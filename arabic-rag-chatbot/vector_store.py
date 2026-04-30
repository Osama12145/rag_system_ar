"""
vector_store.py - Qdrant Vector Database Manager
"""

import asyncio
from datetime import datetime, timezone
import logging
import uuid
from typing import List, Optional, Tuple

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from config import settings

logger = logging.getLogger(__name__)

VECTOR_SIZE = settings.EMBEDDING_DIMENSIONS
EMBED_BATCH_SIZE = 20
EMBED_MAX_RETRIES = 6
EMBED_RATE_LIMIT_WAIT_SECONDS = 65


class VectorStoreManager:
    """
    Manages the Qdrant vector database for document storage and retrieval.
    """

    def __init__(self):
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is required to initialize the vector store.")

        self.embeddings = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.OPENROUTER_API_KEY,
            openai_api_base=settings.EMBEDDING_API_BASE,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )

        if settings.QDRANT_URL == "local":
            self.client = QdrantClient(path="./qdrant_local_db")
        else:
            self.client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None,
            )

        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self._ensure_collection()
        logger.info("Connected to Qdrant successfully")

    def _ensure_collection(self) -> None:
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            logger.info("Creating collection: %s", self.collection_name)
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

    def _get_embed_retry_wait_seconds(self, error: Exception, attempt: int) -> int:
        message = str(error).lower()
        if "429" in message or "rate limit" in message or "tokens per minute" in message:
            return EMBED_RATE_LIMIT_WAIT_SECONDS
        return min(2 ** attempt, 30)

    def _build_payload(self, meta: dict, text: str, chunk_index: int) -> dict:
        page_number = int(meta.get("page_number") or meta.get("page") or 1)
        page_number = max(1, page_number)
        return {
            "page_content": text,
            "source": meta.get("source", ""),
            "source_file": meta.get("source_file", meta.get("source", "")),
            "page": page_number,
            "page_number": page_number,
            "user_id": meta.get("user_id", ""),
            "file_id": meta.get("file_id", ""),
            "chunk_index": meta.get("chunk_index", chunk_index),
            "upload_timestamp": meta.get(
                "upload_timestamp",
                datetime.now(timezone.utc).isoformat(),
            ),
        }

    async def add_documents_to_vectorstore_async(self, documents: List[Document]) -> bool:
        if not documents:
            logger.info("No documents received for indexing")
            return True

        try:
            logger.info("Adding %s documents to Qdrant...", len(documents))
            texts = [doc.page_content for doc in documents]
            metadatas = [doc.metadata for doc in documents]

            vectors = []
            total_batches = (len(texts) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE
            for batch_num, start in enumerate(range(0, len(texts), EMBED_BATCH_SIZE), start=1):
                batch_texts = texts[start : start + EMBED_BATCH_SIZE]
                for attempt in range(EMBED_MAX_RETRIES):
                    try:
                        batch_vectors = await asyncio.to_thread(self.embeddings.embed_documents, batch_texts)
                        vectors.extend(batch_vectors)
                        logger.info("Embedded batch %s/%s", batch_num, total_batches)
                        break
                    except Exception as e:
                        if attempt == EMBED_MAX_RETRIES - 1:
                            raise
                        wait_seconds = self._get_embed_retry_wait_seconds(e, attempt)
                        logger.warning(
                            "Embed attempt %s failed for batch %s/%s, retrying in %ss: %s",
                            attempt + 1,
                            batch_num,
                            total_batches,
                            wait_seconds,
                            e,
                        )
                        await asyncio.sleep(wait_seconds)

            points = []
            for i, (vector, text, meta) in enumerate(zip(vectors, texts, metadatas)):
                point_id = str(uuid.uuid4())
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=self._build_payload(meta, text, i),
                    )
                )

            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                await asyncio.to_thread(
                    self.client.upsert,
                    collection_name=self.collection_name,
                    points=batch,
                )
                logger.info("Uploaded batch %s", i // batch_size + 1)

            logger.info("All documents added successfully")
            return True
        except Exception as e:
            logger.error("Error adding documents: %s", e)
            return False

    def add_documents_to_vectorstore(self, documents: List[Document]) -> bool:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.add_documents_to_vectorstore_async(documents))
        raise RuntimeError("Use add_documents_to_vectorstore_async inside a running event loop")

    def search_documents(
        self,
        query: str,
        top_k: int = None,
        threshold: float = None,
        user_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        source_files: Optional[List[str]] = None,
    ) -> List[Tuple[Document, float]]:
        if top_k is None:
            top_k = settings.TOP_K_DOCUMENTS
        if threshold is None:
            threshold = settings.SIMILARITY_THRESHOLD

        try:
            logger.info("Searching for: '%s'", query)
            query_vector = self.embeddings.embed_query(query)

            must_conditions = []
            if user_id:
                must_conditions.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))
            if file_ids:
                must_conditions.append(FieldCondition(key="file_id", match=MatchAny(any=file_ids)))
            if source_files:
                must_conditions.append(FieldCondition(key="source_file", match=MatchAny(any=source_files)))

            query_filter = Filter(must=must_conditions) if must_conditions else None
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                query_filter=query_filter,
            )

            filtered_results = []
            for point in results.points:
                score = point.score
                if score >= threshold:
                    page_number = int(
                        point.payload.get("page_number") or point.payload.get("page") or 1
                    )
                    page_number = max(1, page_number)
                    doc = Document(
                        page_content=point.payload.get("page_content", ""),
                        metadata={
                            "source": point.payload.get("source", ""),
                            "source_file": point.payload.get(
                                "source_file", point.payload.get("source", "")
                            ),
                            "page": page_number,
                            "page_number": page_number,
                            "user_id": point.payload.get("user_id", ""),
                            "file_id": point.payload.get("file_id", ""),
                            "chunk_index": point.payload.get("chunk_index", 0),
                            "upload_timestamp": point.payload.get("upload_timestamp", ""),
                        },
                    )
                    filtered_results.append((doc, score))

            logger.info("Found %s relevant documents", len(filtered_results))
            return filtered_results
        except Exception as e:
            logger.error("Search error: %s", e)
            return []

    def get_documents_by_file_ids(
        self,
        *,
        user_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Document]:
        if not file_ids:
            return []

        try:
            must_conditions = [FieldCondition(key="file_id", match=MatchAny(any=file_ids))]
            if user_id:
                must_conditions.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))

            documents: List[Document] = []
            offset = None
            while True:
                points, offset = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(must=must_conditions),
                    limit=min(limit or 256, 256),
                    with_payload=True,
                    with_vectors=False,
                    offset=offset,
                )

                for point in points:
                    page_number = int(point.payload.get("page_number") or point.payload.get("page") or 1)
                    page_number = max(1, page_number)
                    documents.append(
                        Document(
                            page_content=point.payload.get("page_content", ""),
                            metadata={
                                "source": point.payload.get("source", ""),
                                "source_file": point.payload.get(
                                    "source_file", point.payload.get("source", "")
                                ),
                                "page": page_number,
                                "page_number": page_number,
                                "user_id": point.payload.get("user_id", ""),
                                "file_id": point.payload.get("file_id", ""),
                                "chunk_index": point.payload.get("chunk_index", 0),
                                "upload_timestamp": point.payload.get("upload_timestamp", ""),
                            },
                        )
                    )
                    if limit and len(documents) >= limit:
                        break

                if (limit and len(documents) >= limit) or offset is None:
                    break

            documents.sort(
                key=lambda doc: (
                    str(doc.metadata.get("source_file", "")),
                    int(doc.metadata.get("page_number") or 1),
                    int(doc.metadata.get("chunk_index") or 0),
                )
            )
            logger.info("Fetched %s chunks directly for file_ids=%s", len(documents), file_ids)
            return documents
        except Exception as e:
            logger.error("Direct file fetch error: %s", e)
            return []

    def list_user_source_files(self, user_id: Optional[str] = None) -> List[str]:
        must_conditions = []
        if user_id:
            must_conditions.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))

        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(must=must_conditions) if must_conditions else None,
            limit=512,
            with_payload=True,
            with_vectors=False,
        )

        seen = set()
        filenames: List[str] = []
        for point in points:
            source_file = point.payload.get("source_file") or point.payload.get("source")
            if source_file and source_file not in seen:
                seen.add(source_file)
                filenames.append(source_file)
        return filenames

    def get_file_ids_by_source_files(
        self,
        user_id: Optional[str] = None,
        source_files: Optional[List[str]] = None,
    ) -> List[str]:
        if not source_files:
            return []

        must_conditions = [FieldCondition(key="source_file", match=MatchAny(any=source_files))]
        if user_id:
            must_conditions.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))

        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(must=must_conditions),
            limit=512,
            with_payload=True,
            with_vectors=False,
        )

        seen = set()
        file_ids: List[str] = []
        for point in points:
            file_id = point.payload.get("file_id")
            if file_id and file_id not in seen:
                seen.add(file_id)
                file_ids.append(file_id)
        return file_ids

    def get_latest_file_id(self, user_id: Optional[str] = None) -> Optional[str]:
        must_conditions = []
        if user_id:
            must_conditions.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))

        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(must=must_conditions) if must_conditions else None,
            limit=512,
            with_payload=True,
            with_vectors=False,
        )

        latest_ts = ""
        latest_file_id = None
        for point in points:
            file_id = point.payload.get("file_id")
            ts = point.payload.get("upload_timestamp", "")
            if file_id and ts > latest_ts:
                latest_ts = ts
                latest_file_id = file_id

        return latest_file_id

    def delete_all_documents(self) -> bool:
        try:
            self.client.delete_collection(self.collection_name)
            self._ensure_collection()
            logger.info("All documents deleted, collection recreated")
            return True
        except Exception as e:
            logger.error("Delete error: %s", e)
            return False

    def delete_documents_for_user(self, user_id: str) -> bool:
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
                    )
                ),
            )
            logger.info("Deleted Qdrant documents for user %s", user_id)
            return True
        except Exception as e:
            logger.error("Delete error for user %s: %s", user_id, e)
            return False

    def get_index_stats(self) -> dict:
        try:
            stats = self.client.get_collection(self.collection_name)
            return {
                "total_vectors": stats.points_count,
                "status": str(stats.status),
            }
        except Exception as e:
            logger.error("Stats error: %s", e)
            return {}


if __name__ == "__main__":
    vs_manager = VectorStoreManager()
    results = vs_manager.search_documents("What is the leave policy?")
    for doc, score in results:
        print(f"\n--- Score: {score:.2f} ---")
        print(doc.page_content[:300])
