"""
OpenAlex Scholarly Source Adapter.
Queries the OpenAlex REST API using polite pool standards, extracts open-access metadata,
and normalizes records.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OPENALEX_BASE_URL = "https://api.openalex.org/works"


class OpenAlexAdapter:
    """Adapter for retrieving academic literature from OpenAlex."""

    def __init__(self, email: Optional[str] = None, timeout: Optional[int] = None):
        self.email = email or settings.OPENALEX_EMAIL
        self.timeout = timeout or settings.SEARCH_TIMEOUT_SECONDS

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search OpenAlex works for the given query string."""
        if not query or not query.strip():
            return []

        # Sanitize query for OpenAlex search engine (strip punctuation like ?, :, quotes, limit length)
        import re
        clean_q = re.sub(r"[^\w\s\-]", " ", query).replace("_", " ").strip()
        clean_q = re.sub(r"\s+", " ", clean_q)
        words = clean_q.split()
        if len(words) > 8:
            clean_q = " ".join(words[:8])

        params: Dict[str, Any] = {
            "search": clean_q or query.strip(),
            "per-page": min(limit, 25),
        }
        if self.email and "@" in self.email:
            params["mailto"] = self.email

        headers = {
            "User-Agent": f"AutonomousResearchAssistant/1.0 (mailto:{self.email})",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(OPENALEX_BASE_URL, params=params, headers=headers)
                if response.status_code == 429:
                    logger.warning("OpenAlex rate limit encountered (HTTP 429) for query '%s'. Proceeding with available sources.", query)
                    return []
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as e:
            logger.warning("OpenAlex query timed out after %ss for query '%s': %s", self.timeout, query, e)
            return []
        except httpx.HTTPError as e:
            logger.warning("OpenAlex search failed for query '%s': %s", query, e)
            return []
        except Exception as e:
            logger.error("Unexpected error in OpenAlex search: %s", e)
            return []

        results: List[Dict[str, Any]] = []
        for item in data.get("results", []):
            normalized = self._normalize_work(item)
            if normalized:
                results.append(normalized)
        return results

    def _normalize_work(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = item.get("title")
        if not title:
            return None

        # Authors
        authors: List[str] = []
        for authorship in item.get("authorships", []):
            author_name = authorship.get("author", {}).get("display_name")
            if author_name:
                authors.append(author_name)

        # DOI
        doi_raw = item.get("doi")
        doi = None
        if doi_raw:
            doi = doi_raw.replace("https://doi.org/", "").strip()

        # arXiv ID from ids dict or doi
        ids = item.get("ids") or {}
        arxiv_url = ids.get("arxiv")
        arxiv_id = None
        if arxiv_url:
            import re
            m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]+\.[0-9]+(?:v[0-9]+)?)", arxiv_url, re.IGNORECASE)
            if m:
                arxiv_id = m.group(1)
        if not arxiv_id and doi and "arxiv" in doi.lower():
            import re
            m = re.search(r"arxiv\.([0-9]+\.[0-9]+(?:v[0-9]+)?)", doi, re.IGNORECASE)
            if m:
                arxiv_id = m.group(1)

        # Reconstruct abstract from inverted index if present
        abstract = self._reconstruct_abstract(item.get("abstract_inverted_index"))

        # Access and PDF URL
        open_access = item.get("open_access", {})
        is_oa = open_access.get("is_oa", False)
        oa_url = open_access.get("oa_url")
        pdf_url = None
        primary_location = item.get("primary_location") or {}
        if primary_location.get("pdf_url"):
            pdf_url = primary_location.get("pdf_url")
        elif oa_url and (oa_url.lower().endswith(".pdf") or "pdf" in oa_url.lower()):
            pdf_url = oa_url

        # Initial access status prior to actual document extraction
        if pdf_url:
            access_status = "full_text_open"
        elif abstract:
            access_status = "abstract_only"
        else:
            access_status = "metadata_only"

        canonical_url = doi_raw or item.get("id") or (f"https://doi.org/{doi}" if doi else None)

        venue_display = (primary_location.get("source") or {}).get("display_name")
        return {
            "title": title.strip(),
            "authors": authors[:10] if authors else ["Unknown Author"],
            "publication_year": item.get("publication_year"),
            "abstract": abstract,
            "doi": doi,
            "arxiv_id": arxiv_id,
            "canonical_url": canonical_url,
            "pdf_url": pdf_url,
            "venue": venue_display,
            "provider": "openalex",
            "access_status": access_status,
            "doc_type": item.get("type", "journal-article"),
            "raw_metadata": {
                "openalex_id": item.get("id"),
                "cited_by_count": item.get("cited_by_count", 0),
                "is_oa": is_oa,
                "venue": venue_display,
                "primary_location": primary_location,
                "type": item.get("type"),
            },
        }

    def _reconstruct_abstract(self, inverted_index: Optional[Dict[str, List[int]]]) -> Optional[str]:
        if not inverted_index:
            return None
        try:
            word_positions: List[tuple[int, str]] = []
            for word, positions in inverted_index.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort(key=lambda x: x[0])
            return " ".join(word for _, word in word_positions)
        except Exception:
            return None
