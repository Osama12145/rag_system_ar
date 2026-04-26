"""
document_processor.py - Document Processing Pipeline
Handles loading, splitting, and cleaning documents for the RAG system.
"""

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from pathlib import Path
from typing import List
import io
import logging
import re
import shutil
from config import settings

try:
    import fitz  # pymupdf
except ImportError:  # pragma: no cover - dependency added via requirements.txt
    fitz = None

try:
    import pytesseract
except ImportError:  # pragma: no cover - dependency added via requirements.txt
    pytesseract = None

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - dependency added via requirements.txt
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
            separators=["\n\n", "\n", " ", ""]
        )

    def _score_ocr_text(self, text: str) -> int:
        """Prefer OCR output that contains more real words and fewer noisy symbols."""
        compact_text = " ".join(text.split())
        if not compact_text:
            return 0

        word_count = sum(1 for word in re.findall(r"\w+", compact_text, flags=re.UNICODE) if len(word) >= 3)
        alpha_numeric_count = sum(1 for char in compact_text if char.isalnum())
        noisy_symbol_count = sum(1 for char in compact_text if char in "@#%^*_=`~|<>")
        return (word_count * 10) + alpha_numeric_count - (noisy_symbol_count * 3)

    def _extract_ocr_text(self, page, file_name: str) -> str:
        """Try multiple OCR passes and keep the most text-like result."""
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
                    logger.debug("OCR attempt failed for %s using %s/%s: %s", file_name, lang, variant_name, ocr_error)
                    continue

                candidate_score = self._score_ocr_text(candidate_text)
                if candidate_score > best_score:
                    best_text = candidate_text
                    best_score = candidate_score

        return best_text

    def _extract_text_with_ocr_fallback(self, file_path: Path) -> List[Document]:
        """
        Extract PDF text page by page and use OCR only when native extraction is nearly empty.
        If OCR tooling is unavailable, continue with standard extraction instead of failing.
        """
        if fitz is None:
            raise RuntimeError("PyMuPDF is not installed")

        tesseract_binary = shutil.which("tesseract")
        ocr_ready = bool(tesseract_binary and pytesseract is not None and Image is not None and ImageOps is not None)

        if tesseract_binary and pytesseract is not None:
            pytesseract.pytesseract.tesseract_cmd = tesseract_binary
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
            for page_num, page in enumerate(pdf_document):
                text = page.get_text().strip()

                if len(text) >= 50:
                    documents.append(
                        Document(
                            page_content=text,
                            metadata={"source": file_path.name, "page": page_num},
                        )
                    )
                    continue

                if ocr_ready:
                    logger.info("Page %s in %s has low extractable text, running OCR", page_num, file_path.name)
                    try:
                        ocr_text = self._extract_ocr_text(page, file_path.name)
                    except Exception as ocr_error:
                        logger.warning("OCR failed on page %s in %s: %s", page_num, file_path.name, ocr_error)
                        ocr_text = ""

                    if ocr_text:
                        documents.append(
                            Document(
                                page_content=ocr_text,
                                metadata={"source": file_path.name, "page": page_num},
                            )
                        )
                        continue

                if text:
                    documents.append(
                        Document(
                            page_content=text,
                            metadata={"source": file_path.name, "page": page_num},
                        )
                    )
                else:
                    logger.warning(
                        "Page %s in %s produced no extractable text and OCR did not add content",
                        page_num,
                        file_path.name,
                    )
        finally:
            pdf_document.close()

        return documents
        
    def load_documents(self, directory_path: str) -> List[Document]:
        """
        Load all documents from a directory.
        Supports: PDF, DOCX, TXT
        """
        documents = []
        path = Path(directory_path)

        logger.info(f"Loading documents from: {directory_path}")

        # Load PDF files
        for pdf_file in path.glob("*.pdf"):
            try:
                if fitz is not None:
                    docs = self._extract_text_with_ocr_fallback(pdf_file)
                else:
                    logger.warning("PyMuPDF unavailable, falling back to PyPDFLoader for %s", pdf_file.name)
                    loader = PyPDFLoader(str(pdf_file))
                    docs = loader.load()
                    for d in docs:
                        d.metadata["source"] = pdf_file.name
                logger.info(f"Loaded: {pdf_file.name} ({len(docs)} pages)")
                documents.extend(docs)
            except Exception as e:
                logger.error(f"Error loading {pdf_file.name}: {e}")

        # Load Word files
        for docx_file in path.glob("*.docx"):
            try:
                loader = Docx2txtLoader(str(docx_file))
                docs = loader.load()
                for d in docs:
                    d.metadata["source"] = docx_file.name
                logger.info(f"Loaded: {docx_file.name}")
                documents.extend(docs)
            except Exception as e:
                logger.error(f"Error loading {docx_file.name}: {e}")

        # Load text files
        for txt_file in path.glob("*.txt"):
            try:
                loader = TextLoader(str(txt_file), encoding='utf-8')
                docs = loader.load()
                for d in docs:
                    d.metadata["source"] = txt_file.name
                logger.info(f"Loaded: {txt_file.name}")
                documents.extend(docs)
            except Exception as e:
                logger.error(f"Error loading {txt_file.name}: {e}")

        logger.info(f"Total documents loaded: {len(documents)}")
        return documents
    
    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        Split long documents into smaller chunks with overlap.
        """
        logger.info("Splitting documents into chunks...")
        
        all_chunks = []
        for doc in documents:
            chunks = self.text_splitter.split_text(doc.page_content)
            
            for i, chunk in enumerate(chunks):
                chunk_doc = Document(
                    page_content=chunk,
                    metadata={
                        **doc.metadata,
                        "chunk_index": i,
                        "source": doc.metadata.get("source", "unknown")
                    }
                )
                all_chunks.append(chunk_doc)
        
        logger.info(f"Split into {len(all_chunks)} chunks")
        return all_chunks
    
    def clean_documents(self, documents: List[Document]) -> List[Document]:
        """
        Clean documents by removing extra whitespace and empty lines.
        """
        cleaned = []
        for doc in documents:
            cleaned_content = "\n".join(
                line.strip() for line in doc.page_content.split("\n") 
                if line.strip()
            )
            
            if len(cleaned_content) > 10:  # Skip very short chunks
                doc.page_content = cleaned_content
                cleaned.append(doc)
        
        logger.info(f"Cleaned {len(cleaned)} documents")
        return cleaned
    
    def process_documents(self, directory_path: str) -> List[Document]:
        """
        Main processing pipeline: load -> split -> clean
        """
        documents = self.load_documents(directory_path)
        chunks = self.split_documents(documents)
        cleaned = self.clean_documents(chunks)
        return cleaned


if __name__ == "__main__":
    processor = DocumentProcessor()
    docs = processor.process_documents("./documents")
    
    for i, doc in enumerate(docs[:3]):
        print(f"\n--- Chunk {i} ---")
        print(doc.page_content[:200])
        print(f"Source: {doc.metadata}")
