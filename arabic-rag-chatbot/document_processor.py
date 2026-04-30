"""
document_processor.py - Document Processing Pipeline
Handles loading, splitting, and cleaning documents for the RAG system.
"""

import asyncio
import io
import logging
import mimetypes
from pathlib import Path
import re
import shutil
from typing import Any, List, Optional, Tuple

import httpx
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings

try:
    import fitz  # pymupdf
except ImportError:  # pragma: no cover
    fitz = None

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Processes documents by loading, splitting, and cleaning them.
    """

    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""],
        )

    def _use_remote_ocr(self) -> bool:
        return settings.OCR_PROVIDER.lower() == "excai" and bool(settings.EXCAI_OCR_API_KEY)

    def _score_ocr_text(self, text: str) -> int:
        compact_text = " ".join(text.split())
        if not compact_text:
            return 0

        word_count = sum(1 for word in re.findall(r"\w+", compact_text, flags=re.UNICODE) if len(word) >= 3)
        alpha_numeric_count = sum(1 for char in compact_text if char.isalnum())
        noisy_symbol_count = sum(1 for char in compact_text if char in "@#%^*_=`~|<>")
        return (word_count * 10) + alpha_numeric_count - (noisy_symbol_count * 3)

    def _extract_ocr_text(self, page, file_name: str) -> str:
        pix = page.get_pixmap(dpi=400)
        base_image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
        enhanced_image = ImageOps.autocontrast(base_image)
        threshold_image = enhanced_image.point(lambda px: 255 if px > 160 else 0)

        best_text = ""
        best_score = 0
        variants = [
            ("enhanced", enhanced_image),
            ("threshold", threshold_image),
            ("grayscale", base_image),
        ]
        language_candidates = ["ara+eng", "eng", "ara"]

        for lang in language_candidates:
            for variant_name, image in variants:
                try:
                    candidate_text = pytesseract.image_to_string(image, lang=lang, config="--psm 6").strip()
                except Exception as ocr_error:
                    logger.debug(
                        "OCR attempt failed for %s using %s/%s: %s",
                        file_name,
                        lang,
                        variant_name,
                        ocr_error,
                    )
                    continue

                candidate_score = self._score_ocr_text(candidate_text)
                if candidate_score > best_score:
                    best_text = candidate_text
                    best_score = candidate_score

        return best_text

    def _build_page_documents(
        self,
        file_name: str,
        payload: dict,
        extracted_text: str,
        page_count: int,
        upload_timestamp: Optional[str] = None,
    ) -> List[Document]:
        per_page_items = payload.get("pages") or payload.get("pageTexts") or payload.get("page_texts") or []
        page_documents: List[Document] = []

        if isinstance(per_page_items, list) and per_page_items:
            for index, item in enumerate(per_page_items, start=1):
                if isinstance(item, dict):
                    page_text = (item.get("text") or item.get("content") or "").strip()
                    page_number = int(item.get("page") or item.get("page_number") or index)
                else:
                    page_text = str(item).strip()
                    page_number = index

                if not page_text:
                    continue

                metadata = {
                    "source": file_name,
                    "source_file": file_name,
                    "page_number": max(1, page_number),
                    "page": max(1, page_number),
                }
                if upload_timestamp:
                    metadata["upload_timestamp"] = upload_timestamp
                page_documents.append(Document(page_content=page_text, metadata=metadata))

            if page_documents:
                return page_documents

        raw_segments = [segment.strip() for segment in re.split(r"\f+", extracted_text) if segment.strip()]
        if len(raw_segments) <= 1:
            raw_segments = [
                segment.strip()
                for segment in re.split(r"(?=^\s*(?:Page\s+\d+|صفحة\s+\d+)\b)", extracted_text, flags=re.MULTILINE)
                if segment.strip()
            ]

        if len(raw_segments) <= 1:
            marker_pattern = re.compile(r"(?:^|\n)\s*(Page\s+\d+|صفحة\s+\d+)\b", flags=re.MULTILINE)
            marker_matches = list(marker_pattern.finditer(extracted_text))
            reconstructed_segments: List[str] = []
            if marker_matches:
                for idx, match in enumerate(marker_matches):
                    start = match.start()
                    end = marker_matches[idx + 1].start() if idx + 1 < len(marker_matches) else len(extracted_text)
                    segment = extracted_text[start:end].strip()
                    if segment:
                        reconstructed_segments.append(segment)
            if reconstructed_segments:
                raw_segments = reconstructed_segments

        if len(raw_segments) <= 1:
            logger.info(
                "ExcAI OCR returned combined text for %s without page markers; estimating %s page(s)",
                file_name,
                page_count,
            )
            total_length = len(extracted_text)
            estimated_segments: List[str] = []
            cursor = 0
            for index in range(page_count):
                start = cursor if index > 0 else (index * total_length) // page_count
                end = ((index + 1) * total_length) // page_count
                end_adjusted = max(
                    extracted_text.rfind("\n", start, end),
                    extracted_text.rfind(" ", start, end),
                )
                if end_adjusted == -1 or end_adjusted <= start:
                    end_adjusted = end
                end = end_adjusted

                segment = extracted_text[start:end].strip()
                if segment:
                    estimated_segments.append(segment)
                cursor = end
            raw_segments = estimated_segments or [extracted_text]

        page_documents = []
        for index, segment in enumerate(raw_segments, start=1):
            cleaned_segment = re.sub(r"^\s*(?:Page\s+\d+|صفحة\s+\d+)\s*", "", segment, flags=re.MULTILINE).strip()
            if not cleaned_segment:
                continue
            metadata = {
                "source": file_name,
                "source_file": file_name,
                "page_number": index,
                "page": index,
            }
            if upload_timestamp:
                metadata["upload_timestamp"] = upload_timestamp
            page_documents.append(Document(page_content=cleaned_segment, metadata=metadata))
        return page_documents

    async def _extract_text_with_excai_ocr_async(
        self,
        file_path: Path,
        upload_timestamp: Optional[str] = None,
    ) -> List[Document]:
        if not self._use_remote_ocr():
            return []

        endpoint = f"{settings.EXCAI_OCR_BASE_URL.rstrip('/')}/ocr/extract"
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

        with file_path.open("rb") as file_handle:
            files = {"file": (file_path.name, file_handle, content_type)}
            async with httpx.AsyncClient(timeout=settings.EXCAI_OCR_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    endpoint,
                    headers={"X-API-Key": settings.EXCAI_OCR_API_KEY or ""},
                    files=files,
                )

        response.raise_for_status()
        payload = response.json()
        extracted_text = (payload.get("text") or "").strip()
        if not extracted_text:
            return []

        page_count = max(1, int(payload.get("pagesCount") or payload.get("page_count") or 1))
        return self._build_page_documents(
            file_path.name,
            payload,
            extracted_text,
            page_count,
            upload_timestamp=upload_timestamp,
        )

    async def _extract_text_with_ocr_fallback_async(
        self,
        file_path: Path,
        upload_timestamp: Optional[str] = None,
    ) -> List[Document]:
        if fitz is None:
            raise RuntimeError("PyMuPDF is not installed")

        tesseract_binary = shutil.which("tesseract")
        ocr_ready = bool(tesseract_binary and pytesseract is not None and Image is not None and ImageOps is not None)

        if tesseract_binary and pytesseract is not None:
            pytesseract.pytesseract.tesseract_cmd = tesseract_binary
        elif self._use_remote_ocr():
            logger.info("ExcAI OCR is configured; local Tesseract is optional for %s", file_path.name)
        elif pytesseract is not None and Image is not None:
            logger.warning(
                "Tesseract binary not found; scanned PDF pages without extractable text may be skipped for %s",
                file_path.name,
            )
        else:
            logger.warning(
                "OCR dependencies are incomplete; using standard PDF extraction only for %s",
                file_path.name,
            )

        documents: List[Document] = []
        pdf_document = fitz.open(file_path)
        try:
            page_count = len(pdf_document)
            scanned_candidates: List[Tuple[int, Any, str]] = []
            total_native_chars = 0

            for page_num, page in enumerate(pdf_document):
                text = page.get_text().strip()
                metadata = {
                    "source": file_path.name,
                    "source_file": file_path.name,
                    "page_number": page_num + 1,
                    "page": page_num + 1,
                }
                if upload_timestamp:
                    metadata["upload_timestamp"] = upload_timestamp

                if len(text) >= 50:
                    total_native_chars += len(text)
                    documents.append(Document(page_content=text, metadata=metadata))
                    continue

                scanned_candidates.append((page_num, page, text))

            scanned_ratio = (len(scanned_candidates) / page_count) if page_count else 0.0
            should_use_remote_ocr = (
                self._use_remote_ocr()
                and scanned_candidates
                and (
                    scanned_ratio >= settings.OCR_REMOTE_SCANNED_RATIO_THRESHOLD
                    or total_native_chars < settings.OCR_REMOTE_MIN_NATIVE_CHARS
                )
            )

            if should_use_remote_ocr:
                try:
                    logger.info(
                        "Document %s appears scanned-heavy (ratio=%.2f, native_chars=%s), using ExcAI OCR",
                        file_path.name,
                        scanned_ratio,
                        total_native_chars,
                    )
                    remote_documents = await self._extract_text_with_excai_ocr_async(
                        file_path,
                        upload_timestamp=upload_timestamp,
                    )
                    if remote_documents:
                        return remote_documents
                    logger.warning("ExcAI OCR returned no text for %s, falling back to local OCR", file_path.name)
                except Exception as remote_ocr_error:
                    logger.warning("ExcAI OCR failed for %s: %s", file_path.name, remote_ocr_error)

            for page_num, page, text in scanned_candidates:
                metadata = {
                    "source": file_path.name,
                    "source_file": file_path.name,
                    "page_number": page_num + 1,
                    "page": page_num + 1,
                }
                if upload_timestamp:
                    metadata["upload_timestamp"] = upload_timestamp

                if ocr_ready:
                    logger.info("Page %s in %s has low extractable text, running OCR", page_num + 1, file_path.name)
                    try:
                        ocr_text = self._extract_ocr_text(page, file_path.name)
                    except Exception as ocr_error:
                        logger.warning("OCR failed on page %s in %s: %s", page_num + 1, file_path.name, ocr_error)
                        ocr_text = ""

                    if ocr_text:
                        documents.append(Document(page_content=ocr_text, metadata=metadata))
                        continue

                if text:
                    documents.append(Document(page_content=text, metadata=metadata))
                else:
                    logger.warning(
                        "Page %s in %s produced no extractable text and OCR did not add content",
                        page_num + 1,
                        file_path.name,
                    )
        finally:
            pdf_document.close()

        return documents

    async def load_documents_async(
        self,
        directory_path: str,
        upload_timestamp: Optional[str] = None,
    ) -> List[Document]:
        documents: List[Document] = []
        path = Path(directory_path)
        logger.info("Loading documents from: %s", directory_path)

        for pdf_file in path.glob("*.pdf"):
            try:
                if fitz is not None:
                    docs = await self._extract_text_with_ocr_fallback_async(
                        pdf_file,
                        upload_timestamp=upload_timestamp,
                    )
                else:
                    logger.warning("PyMuPDF unavailable, falling back to PyPDFLoader for %s", pdf_file.name)
                    loader = PyPDFLoader(str(pdf_file))
                    docs = await asyncio.to_thread(loader.load)
                    for d in docs:
                        d.metadata["source"] = pdf_file.name
                        d.metadata["source_file"] = pdf_file.name
                        d.metadata["page_number"] = int(d.metadata.get("page", 0)) + 1
                        d.metadata["page"] = int(d.metadata.get("page", 0)) + 1
                        if upload_timestamp:
                            d.metadata["upload_timestamp"] = upload_timestamp
                logger.info("Loaded: %s (%s pages)", pdf_file.name, len(docs))
                documents.extend(docs)
            except Exception as e:
                logger.error("Error loading %s: %s", pdf_file.name, e)

        for docx_file in path.glob("*.docx"):
            try:
                loader = Docx2txtLoader(str(docx_file))
                docs = await asyncio.to_thread(loader.load)
                for d in docs:
                    d.metadata["source"] = docx_file.name
                    d.metadata["source_file"] = docx_file.name
                    d.metadata["page_number"] = 1
                    d.metadata["page"] = 1
                    if upload_timestamp:
                        d.metadata["upload_timestamp"] = upload_timestamp
                logger.info("Loaded: %s", docx_file.name)
                documents.extend(docs)
            except Exception as e:
                logger.error("Error loading %s: %s", docx_file.name, e)

        for txt_file in path.glob("*.txt"):
            try:
                loader = TextLoader(str(txt_file), encoding="utf-8")
                docs = await asyncio.to_thread(loader.load)
                for d in docs:
                    d.metadata["source"] = txt_file.name
                    d.metadata["source_file"] = txt_file.name
                    d.metadata["page_number"] = 1
                    d.metadata["page"] = 1
                    if upload_timestamp:
                        d.metadata["upload_timestamp"] = upload_timestamp
                logger.info("Loaded: %s", txt_file.name)
                documents.extend(docs)
            except Exception as e:
                logger.error("Error loading %s: %s", txt_file.name, e)

        logger.info("Total documents loaded: %s", len(documents))
        return documents

    def load_documents(self, directory_path: str) -> List[Document]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.load_documents_async(directory_path))
        raise RuntimeError("Use load_documents_async inside a running event loop")

    def split_documents(self, documents: List[Document]) -> List[Document]:
        logger.info("Splitting documents into chunks...")
        all_chunks: List[Document] = []
        for doc in documents:
            source_file = doc.metadata.get("source_file") or doc.metadata.get("source") or "unknown"
            page_number = int(doc.metadata.get("page_number") or doc.metadata.get("page") or 1)
            page_number = max(1, page_number)
            chunks = self.text_splitter.split_text(doc.page_content)

            for i, chunk in enumerate(chunks):
                metadata = {
                    **doc.metadata,
                    "chunk_index": i,
                    "source": source_file,
                    "source_file": source_file,
                    "page_number": page_number,
                    "page": page_number,
                }
                all_chunks.append(Document(page_content=chunk, metadata=metadata))

        logger.info("Split into %s chunks", len(all_chunks))
        return all_chunks

    def clean_documents(self, documents: List[Document]) -> List[Document]:
        cleaned = []
        for doc in documents:
            cleaned_content = "\n".join(line.strip() for line in doc.page_content.split("\n") if line.strip())
            if len(cleaned_content) > 10:
                doc.page_content = cleaned_content
                cleaned.append(doc)

        logger.info("Cleaned %s documents", len(cleaned))
        return cleaned

    async def process_documents_async(
        self,
        directory_path: str,
        upload_timestamp: Optional[str] = None,
    ) -> List[Document]:
        documents = await self.load_documents_async(directory_path, upload_timestamp=upload_timestamp)
        chunks = self.split_documents(documents)
        return self.clean_documents(chunks)

    def process_documents(self, directory_path: str) -> List[Document]:
        documents = self.load_documents(directory_path)
        chunks = self.split_documents(documents)
        return self.clean_documents(chunks)


if __name__ == "__main__":
    processor = DocumentProcessor()
    docs = processor.process_documents("./documents")

    for i, doc in enumerate(docs[:3]):
        print(f"\n--- Chunk {i} ---")
        print(doc.page_content[:200])
        print(f"Source: {doc.metadata}")
