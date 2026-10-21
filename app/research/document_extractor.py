"""
Document Extraction and Text Normalization Module.
Uses PyMuPDF (fitz) for PDF text extraction with abstract segmentation fallback,
sanitizes against prompt injection, and extracts structured evidence passages.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

# Try to import PyMuPDF
try:
    import pymupdf as fitz  # type: ignore
    HAS_PYMUPDF = True
except ImportError:
    try:
        import fitz  # type: ignore
        HAS_PYMUPDF = True
    except ImportError:
        HAS_PYMUPDF = False
        logger.warning("PyMuPDF not found. PDF extraction will rely on abstract fallbacks.")


# Known prompt injection signatures to neutralize from untrusted papers
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"<\s*\|?im_start\|?\s*>", re.IGNORECASE),
    re.compile(r"<\s*\|?im_end\|?\s*>", re.IGNORECASE),
    re.compile(r"\[\s*INST\s*\].*?\[\s*/\s*INST\s*\]", re.IGNORECASE | re.DOTALL),
]


class DocumentExtractor:
    """Extracts, cleans, and chunks text from academic sources (PDF or abstract)."""

    @classmethod
    def sanitize_untrusted_text(cls, text: str) -> str:
        """Neutralize malicious injection attempts embedded in academic papers."""
        cleaned = text
        for pattern in PROMPT_INJECTION_PATTERNS:
            cleaned = pattern.sub("[FILTERED_INJECTION_ATTEMPT]", cleaned)
        # Remove control characters
        cleaned = "".join(ch for ch in cleaned if ch == "\n" or ch == "\t" or ch >= " ")
        return cleaned.strip()

    @classmethod
    async def extract_from_pdf_url(
        cls, pdf_url: str, max_pages: int = 8, timeout: int = 15
    ) -> List[Dict[str, Any]]:
        """Download and extract passages from an open-access PDF using PyMuPDF."""
        if not HAS_PYMUPDF or not pdf_url:
            return []

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(pdf_url)
                if resp.status_code != 200 or not resp.content:
                    return []
                pdf_bytes = resp.content
        except Exception as e:
            logger.debug("Failed downloading PDF from %s: %s", pdf_url, e)
            return []

        return cls.extract_from_pdf_bytes(pdf_bytes, max_pages=max_pages)

    @classmethod
    def extract_from_pdf_bytes(
        cls, pdf_bytes: bytes, max_pages: int = 8
    ) -> List[Dict[str, Any]]:
        """Parse PDF byte stream using PyMuPDF and segment into passages."""
        if not HAS_PYMUPDF:
            return []

        passages: List[Dict[str, Any]] = []
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = min(len(doc), max_pages)

            for page_num in range(total_pages):
                page = doc[page_num]
                text = page.get_text("text")
                if not text or len(text.strip()) < 80:
                    continue

                cleaned_page = cls.sanitize_untrusted_text(text)
                # Chunk page text into coherent passage segments (~150-300 words)
                chunks = cls.chunk_text(cleaned_page, target_words=200)
                for chunk in chunks:
                    passages.append({
                        "passage_text": chunk,
                        "page_number": page_num + 1,
                        "extraction_method": "pymupdf_pdf",
                    })
        except Exception as e:
            logger.debug("PyMuPDF parsing exception: %s", e)
            return []

        return passages

    @classmethod
    def extract_from_abstract(cls, abstract_text: str) -> List[Dict[str, Any]]:
        """Segment an academic abstract into standalone evidence passages."""
        if not abstract_text or len(abstract_text.strip()) < 30:
            return []

        cleaned = cls.sanitize_untrusted_text(abstract_text)
        chunks = cls.chunk_text(cleaned, target_words=120)
        return [
            {
                "passage_text": chunk,
                "page_number": 1,
                "extraction_method": "abstract",
            }
            for chunk in chunks
        ]

    @classmethod
    def chunk_text(cls, text: str, target_words: int = 200) -> List[str]:
        """Split text along paragraph or sentence boundaries into chunks of target word length."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_count = 0

        for para in paragraphs:
            words = para.split()
            if current_count + len(words) <= target_words or not current_chunk:
                current_chunk.append(para)
                current_count += len(words)
            else:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_count = len(words)

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        # Filter out tiny residual chunks (< 25 words)
        valid_chunks = [c for c in chunks if len(c.split()) >= 20]
        return valid_chunks if valid_chunks else (chunks if chunks else [text])
