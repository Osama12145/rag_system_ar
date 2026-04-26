import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from typing import Any, Dict, List

from fastapi import UploadFile
from langchain_core.documents import Document

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import api_server
from api_server import upload_documents
from database import init_db
from document_processor import DocumentProcessor
from vector_store import VectorStoreManager


TEST_FILES = {
    "aramco": Path(r"C:\Users\os\OneDrive\Desktop\saudi-aramco-ara-2023-english.pdf"),
    "cv": Path(r"C:\Users\os\OneDrive\Desktop\OSAMA ALI NAJI_Cv.pdf"),
    "degree_ar": Path(r"C:\Users\os\OneDrive\Desktop\OSAMA_NAJI\الوثيقة.pdf"),
}


def shorten(text: str, limit: int = 180) -> str:
    return " ".join(text.split())[:limit]


def find_line(lines: List[str], keywords: List[str]) -> str:
    for line in lines:
        normalized = line.lower()
        if all(keyword.lower() in normalized for keyword in keywords):
            return line
    return ""


def extract_file(processor: DocumentProcessor, file_path: Path) -> Dict[str, Any]:
    pages = processor._extract_text_with_ocr_fallback(file_path)
    chunks = processor.clean_documents(processor.split_documents(pages))
    full_text = "\n".join(doc.page_content for doc in pages)
    lines = [line.strip() for line in full_text.splitlines() if line.strip()]

    result = {
        "file": str(file_path),
        "exists": file_path.exists(),
        "pages_extracted": len(pages),
        "chunks_generated": len(chunks),
        "first_snippet": shorten(pages[0].page_content if pages else ""),
        "char_count": len(full_text),
    }

    if file_path.name.startswith("saudi-aramco"):
        result["revenue_line"] = find_line(lines, ["revenue", "2023"]) or find_line(lines, ["revenues"])
        result["dividend_line"] = find_line(lines, ["dividend"])
    elif "Cv" in file_path.name or "Cv" in file_path.stem:
        result["university_line"] = find_line(lines, ["university"]) or find_line(lines, ["جامعة"])
        result["name_line"] = find_line(lines, ["osama"]) or find_line(lines, ["أسامة"])
    else:
        result["university_line"] = find_line(lines, ["جامعة"]) or find_line(lines, ["university"])
        result["document_line"] = lines[0] if lines else ""

    return result


class FakeVectorStore:
    def __init__(self):
        self.added_documents: List[Document] = []

    def add_documents_to_vectorstore(self, documents: List[Document]) -> bool:
        self.added_documents.extend(documents)
        return True


async def exercise_upload(file_path: Path) -> Dict[str, Any]:
    await init_db()
    fake_vs = FakeVectorStore()
    api_server.vs_manager = fake_vs

    with file_path.open("rb") as handle:
        upload_file = UploadFile(filename=file_path.name, file=handle)
        response = await upload_documents(files=[upload_file], x_user_id="upload-test-user")

    return {
        "success": response.success,
        "message": response.message,
        "document_name": response.document.name if response.document else None,
        "document_size": response.document.size if response.document else None,
        "document_pages": response.document.pages if response.document else None,
        "document_chunks": response.document.chunks if response.document else None,
        "vector_docs_received": len(fake_vs.added_documents),
    }


@dataclass
class FakePoint:
    score: float
    payload: Dict[str, Any]


class FakeEmbeddings:
    def __init__(self):
        self.calls: List[int] = []
        self.fail_once_for_size = {50}

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        self.calls.append(len(texts))
        if len(texts) in self.fail_once_for_size:
            self.fail_once_for_size.remove(len(texts))
            raise RuntimeError(f"simulated failure for batch size {len(texts)}")
        return [[float(index)] * 3 for index, _ in enumerate(texts, start=1)]

    def embed_query(self, query: str) -> List[float]:
        return [0.1, 0.2, 0.3]


class FakeClient:
    def __init__(self):
        self.upserts: List[List[Any]] = []
        self.last_query_filter = None
        self.last_delete_filter = None

    def upsert(self, collection_name: str, points: List[Any]) -> None:
        self.upserts.append(points)

    def query_points(self, collection_name: str, query: List[float], limit: int, query_filter: Any):
        self.last_query_filter = query_filter
        return SimpleNamespace(
            points=[
                FakePoint(
                    score=0.9,
                    payload={
                        "page_content": "sample result text",
                        "source": "source.pdf",
                        "page": 3,
                        "user_id": "filter-user",
                        "file_id": "file-123",
                        "chunk_index": 7,
                    },
                )
            ]
        )

    def delete(self, collection_name: str, points_selector: Any) -> None:
        self.last_delete_filter = points_selector


def exercise_vector_store_logic() -> Dict[str, Any]:
    manager = VectorStoreManager.__new__(VectorStoreManager)
    manager.embeddings = FakeEmbeddings()
    manager.client = FakeClient()
    manager.collection_name = "test-collection"

    documents = [
        Document(
            page_content=f"chunk {index}",
            metadata={
                "source": f"file-{index // 3}.pdf",
                "page": index % 10,
                "user_id": "filter-user",
                "file_id": f"f-{index // 3}",
                "chunk_index": index,
            },
        )
        for index in range(120)
    ]

    added = manager.add_documents_to_vectorstore(documents)
    search_results = manager.search_documents("revenue", user_id="filter-user")
    deleted = manager.delete_documents_for_user("filter-user")

    first_payload = manager.client.upserts[0][0].payload if manager.client.upserts else {}
    query_key = manager.client.last_query_filter.must[0].key if manager.client.last_query_filter else None
    delete_key = (
        manager.client.last_delete_filter.filter.must[0].key
        if manager.client.last_delete_filter is not None
        else None
    )

    return {
        "add_documents_ok": added,
        "embed_batch_sizes": manager.embeddings.calls,
        "upsert_batches": [len(batch) for batch in manager.client.upserts],
        "first_payload_keys": sorted(first_payload.keys()),
        "query_filter_key": query_key,
        "delete_filter_key": delete_key,
        "search_result_count": len(search_results),
        "search_result_metadata": search_results[0][0].metadata if search_results else {},
        "delete_documents_ok": deleted,
    }


async def main() -> None:
    processor = DocumentProcessor()
    extraction_results = {
        key: extract_file(processor, path)
        for key, path in TEST_FILES.items()
    }
    upload_result = await exercise_upload(TEST_FILES["aramco"])
    vector_store_result = exercise_vector_store_logic()

    print(
        json.dumps(
            {
                "extraction_results": extraction_results,
                "upload_result": upload_result,
                "vector_store_result": vector_store_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
