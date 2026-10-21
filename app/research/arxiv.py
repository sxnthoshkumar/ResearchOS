"""
arXiv Scholarly Source Adapter.
Queries the arXiv API via Atom/XML feed, normalizes preprints, and extracts metadata.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}


class ArXivAdapter:
    """Adapter for querying arXiv preprints."""

    def __init__(self, timeout: Optional[int] = None):
        self.timeout = timeout or settings.SEARCH_TIMEOUT_SECONDS

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            return []

        # Sanitize and format arXiv search query
        clean_q = re.sub(r"[^\w\s\-\"]", " ", query).replace("_", " ").strip()
        clean_q = re.sub(r"\s+", " ", clean_q)
        words = clean_q.split()
        if len(words) > 8:
            clean_q = " ".join(words[:8])
        encoded_query = f"all:{clean_q}"

        params = {
            "search_query": encoded_query,
            "start": 0,
            "max_results": min(limit, 20),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        headers = {
            "User-Agent": f"AutonomousResearchAssistant/1.0 (academic research client; mailto:{settings.OPENALEX_EMAIL})",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(ARXIV_API_URL, params=params, headers=headers)
                if response.status_code == 429:
                    logger.warning("arXiv rate limit encountered (HTTP 429: Rate exceeded) for query '%s'. Proceeding with available sources.", query)
                    return []
                response.raise_for_status()
                xml_text = response.text
        except httpx.TimeoutException as e:
            logger.warning("arXiv query timed out after %ss for query '%s': %s", self.timeout, query, e)
            return []
        except httpx.HTTPError as e:
            logger.warning("arXiv query failed for '%s': %s", query, e)
            return []
        except Exception as e:
            logger.error("Unexpected error querying arXiv: %s", e)
            return []

        return self._parse_atom_feed(xml_text)

    def _parse_atom_feed(self, xml_text: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error("Failed to parse arXiv Atom feed XML: %s", e)
            return []

        for entry in root.findall("atom:entry", ATOM_NAMESPACE):
            title_elem = entry.find("atom:title", ATOM_NAMESPACE)
            if title_elem is None or not title_elem.text:
                continue
            title = " ".join(title_elem.text.split())

            # Authors
            authors: List[str] = []
            for author_node in entry.findall("atom:author", ATOM_NAMESPACE):
                name_elem = author_node.find("atom:name", ATOM_NAMESPACE)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text.strip())

            # Abstract / summary
            summary_elem = entry.find("atom:summary", ATOM_NAMESPACE)
            abstract = " ".join(summary_elem.text.split()) if summary_elem is not None and summary_elem.text else None

            # Published year
            published_elem = entry.find("atom:published", ATOM_NAMESPACE)
            pub_year = None
            if published_elem is not None and published_elem.text:
                try:
                    pub_year = int(published_elem.text[:4])
                except Exception:
                    pass

            # ID and links
            id_elem = entry.find("atom:id", ATOM_NAMESPACE)
            canonical_url = id_elem.text.strip() if id_elem is not None and id_elem.text else None

            arxiv_id = None
            pdf_url = None
            if canonical_url:
                match = re.search(r"abs/([0-9]+\.[0-9]+(?:v[0-9]+)?)", canonical_url)
                if match:
                    arxiv_id = match.group(1)
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            # Check explicit link tags
            for link in entry.findall("atom:link", ATOM_NAMESPACE):
                if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                    pdf_url = link.attrib.get("href")

            # Check DOI if published later
            doi = None
            doi_elem = entry.find("{http://arxiv.org/schemas/atom}doi")
            if doi_elem is not None and doi_elem.text:
                doi = doi_elem.text.strip()

            # Check journal reference if published later
            journal_ref = None
            jref_elem = entry.find("{http://arxiv.org/schemas/atom}journal_ref")
            if jref_elem is not None and jref_elem.text:
                journal_ref = jref_elem.text.strip()

            # Check author comments
            comment = None
            comment_elem = entry.find("{http://arxiv.org/schemas/atom}comment")
            if comment_elem is not None and comment_elem.text:
                comment = comment_elem.text.strip()

            results.append({
                "title": title,
                "authors": authors[:10] if authors else ["arXiv Contributor"],
                "publication_year": pub_year,
                "abstract": abstract,
                "doi": doi,
                "arxiv_id": arxiv_id,
                "canonical_url": canonical_url,
                "pdf_url": pdf_url,
                "journal_ref": journal_ref,
                "provider": "arxiv",
                "access_status": "full_text_open" if pdf_url else ("abstract_only" if abstract else "metadata_only"),
                "doc_type": "preprint",
                "raw_metadata": {
                    "arxiv_url": canonical_url,
                    "journal_ref": journal_ref,
                    "comment": comment,
                },
            })

        return results
