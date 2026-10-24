"""
Publication Type and Peer-Review Classification Module.

Classifies retrieved scholarly works into explicit categories:
- PEER_REVIEWED_JOURNAL
- PEER_REVIEWED_CONFERENCE
- PREPRINT
- WORKSHOP_OR_OTHER
- TECHNICAL_REPORT
- UNKNOWN

Separates document_type and peer_review_status.
Does NOT assume:
1. Everything on arXiv is permanently unpublished (checks journal_ref, published DOI).
2. Everything indexed in OpenAlex is peer-reviewed (OpenAlex indexes preprints and repositories).
3. A DOI alone proves peer review (repositories issue DOIs for preprints).
4. Missing venue metadata implies preprint status.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

PEER_REVIEW_STATUSES = {
    "PEER_REVIEWED_JOURNAL",
    "PEER_REVIEWED_CONFERENCE",
    "PREPRINT",
    "WORKSHOP_OR_OTHER",
    "TECHNICAL_REPORT",
    "UNKNOWN",
}


class PublicationClassification(BaseModel):
    source_id: str
    title: str
    authors: str
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    venue_name: Optional[str] = None
    publication_year: Optional[int] = None
    document_type: str  # e.g., "journal-article", "proceedings", "preprint", "report"
    publication_status: str  # e.g., "PUBLISHED", "PREPRINT", "IN_PRESS", "UNKNOWN"
    peer_review_status: str  # One of PEER_REVIEW_STATUSES
    classification_evidence: str
    metadata_source: str  # e.g., "openalex", "arxiv_atom", "crossref", "arxiv_journal_ref"
    last_verified_date: str


class PublicationClassifier:
    """Classifies scholarly works using multi-source provenance metadata."""

    def __init__(self, timeout_seconds: int = 4):
        self.timeout = timeout_seconds

    async def classify_source(
        self,
        source: Dict[str, Any],
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> PublicationClassification:
        """Classifies a source into explicit document and peer-review categories."""
        now_str = datetime.now(timezone.utc).isoformat()
        source_id = source.get("id", "unknown_source")
        title = source.get("title", "Untitled Source")
        authors = source.get("authors") or "Unknown"
        doi = source.get("doi")
        arxiv_id = source.get("arxiv_id")
        pub_year = source.get("publication_year")
        provider = (source.get("provider") or "").lower()

        meta = raw_metadata or source.get("raw_metadata") or {}
        if isinstance(meta, str):
            import json
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        # 1. Check for Demo Benchmark records
        if provider == "demo" or "[DEMO" in title.upper() or meta.get("is_demo"):
            doc_type = source.get("doc_type", "demo_synthesis")
            is_preprint = "preprint" in doc_type.lower()
            return PublicationClassification(
                source_id=source_id,
                title=title,
                authors=authors,
                doi=doi,
                arxiv_id=arxiv_id,
                venue_name="Demonstration Benchmark Dataset",
                publication_year=pub_year or 2024,
                document_type="preprint" if is_preprint else "journal-article",
                publication_status="PREPRINT" if is_preprint else "PUBLISHED",
                peer_review_status="PREPRINT" if is_preprint else "PEER_REVIEWED_JOURNAL",
                classification_evidence="Synthetic demonstration record labeled for reproducible benchmarking.",
                metadata_source="demo_engine",
                last_verified_date=now_str,
            )

        # 2. Check for arXiv records
        if provider == "arxiv" or arxiv_id:
            return await self._classify_arxiv_work(source, meta, now_str)

        # 3. Check for OpenAlex records
        if provider == "openalex" or "openalex" in str(source.get("canonical_url", "")).lower():
            return await self._classify_openalex_work(source, meta, now_str)

        # 4. Fallback classification for other providers
        return self._classify_generic_work(source, meta, now_str)

    async def _classify_arxiv_work(
        self,
        source: Dict[str, Any],
        meta: Dict[str, Any],
        now_str: str,
    ) -> PublicationClassification:
        """Classifies an arXiv paper by checking journal-ref, DOI, and comments."""
        source_id = source.get("id", "arxiv_source")
        title = source.get("title", "")
        authors = source.get("authors", "")
        doi = source.get("doi")
        arxiv_id = source.get("arxiv_id")
        pub_year = source.get("publication_year")

        journal_ref = meta.get("journal_ref") or source.get("journal_ref")
        comment = meta.get("comment") or ""

        # Check if arXiv metadata indicates publication in journal or conference
        evidence_parts = []
        if journal_ref:
            evidence_parts.append(f"arXiv metadata contains journal reference: '{journal_ref}'")
            # Analyze venue string
            lower_ref = journal_ref.lower()
            if any(term in lower_ref for term in ("conf", "proc", "symposium", "workshop", "ieee", "acm", "neurips", "icml", "cvpr", "acl")):
                if "workshop" in lower_ref:
                    return PublicationClassification(
                        source_id=source_id,
                        title=title,
                        authors=authors,
                        doi=doi,
                        arxiv_id=arxiv_id,
                        venue_name=journal_ref,
                        publication_year=pub_year,
                        document_type="proceedings-article",
                        publication_status="PUBLISHED",
                        peer_review_status="WORKSHOP_OR_OTHER",
                        classification_evidence="; ".join(evidence_parts),
                        metadata_source="arxiv_journal_ref",
                        last_verified_date=now_str,
                    )
                return PublicationClassification(
                    source_id=source_id,
                    title=title,
                    authors=authors,
                    doi=doi,
                    arxiv_id=arxiv_id,
                    venue_name=journal_ref,
                    publication_year=pub_year,
                    document_type="proceedings-article",
                    publication_status="PUBLISHED",
                    peer_review_status="PEER_REVIEWED_CONFERENCE",
                    classification_evidence="; ".join(evidence_parts),
                    metadata_source="arxiv_journal_ref",
                    last_verified_date=now_str,
                )
            else:
                return PublicationClassification(
                    source_id=source_id,
                    title=title,
                    authors=authors,
                    doi=doi,
                    arxiv_id=arxiv_id,
                    venue_name=journal_ref,
                    publication_year=pub_year,
                    document_type="journal-article",
                    publication_status="PUBLISHED",
                    peer_review_status="PEER_REVIEWED_JOURNAL",
                    classification_evidence="; ".join(evidence_parts),
                    metadata_source="arxiv_journal_ref",
                    last_verified_date=now_str,
                )

        # Check if publisher DOI is assigned (distinct from arXiv repository)
        if doi and not doi.lower().startswith("10.48550"):  # 10.48550 is arXiv's own DOI prefix
            evidence_parts.append(f"External non-arXiv publisher DOI present: {doi}")
            # Cross-verify via Crossref if network permits
            crossref_info = await self._query_crossref(doi)
            if crossref_info:
                venue = crossref_info.get("venue")
                c_type = crossref_info.get("type", "")
                if "proceedings" in c_type or "conference" in c_type:
                    return PublicationClassification(
                        source_id=source_id,
                        title=title,
                        authors=authors,
                        doi=doi,
                        arxiv_id=arxiv_id,
                        venue_name=venue or "Peer-Reviewed Conference",
                        publication_year=pub_year,
                        document_type="proceedings-article",
                        publication_status="PUBLISHED",
                        peer_review_status="PEER_REVIEWED_CONFERENCE",
                        classification_evidence=f"Crossref confirmed conference publication with DOI {doi} at {venue}.",
                        metadata_source="crossref",
                        last_verified_date=now_str,
                    )
                elif "journal" in c_type or venue:
                    return PublicationClassification(
                        source_id=source_id,
                        title=title,
                        authors=authors,
                        doi=doi,
                        arxiv_id=arxiv_id,
                        venue_name=venue or "Peer-Reviewed Journal",
                        publication_year=pub_year,
                        document_type="journal-article",
                        publication_status="PUBLISHED",
                        peer_review_status="PEER_REVIEWED_JOURNAL",
                        classification_evidence=f"Crossref confirmed journal publication with DOI {doi} in {venue}.",
                        metadata_source="crossref",
                        last_verified_date=now_str,
                    )

        # Default for arXiv without external confirmed publication
        return PublicationClassification(
            source_id=source_id,
            title=title,
            authors=authors,
            doi=doi,
            arxiv_id=arxiv_id,
            venue_name="arXiv",
            publication_year=pub_year,
            document_type="preprint",
            publication_status="PREPRINT",
            peer_review_status="PREPRINT",
            classification_evidence="Retrieved from arXiv preprint repository with no journal reference or external peer-reviewed DOI.",
            metadata_source="arxiv_atom",
            last_verified_date=now_str,
        )

    async def _classify_openalex_work(
        self,
        source: Dict[str, Any],
        meta: Dict[str, Any],
        now_str: str,
    ) -> PublicationClassification:
        """Classifies an OpenAlex work distinguishing peer-reviewed venues from preprint servers."""
        source_id = source.get("id", "openalex_source")
        title = source.get("title", "")
        authors = source.get("authors", "")
        doi = source.get("doi")
        arxiv_id = source.get("arxiv_id")
        pub_year = source.get("publication_year")

        raw_type = str(source.get("doc_type") or meta.get("type") or "").lower()
        venue_name = meta.get("venue") or meta.get("host_venue") or meta.get("source_name")
        primary_loc = meta.get("primary_location") or {}
        src_meta = primary_loc.get("source") or {}
        if not venue_name and src_meta.get("display_name"):
            venue_name = src_meta.get("display_name")

        src_type = (src_meta.get("type") or "").lower()  # e.g., "journal", "repository", "conference"
        is_in_doaj = bool(src_meta.get("is_in_doaj", False))

        # Check if repository / preprint server
        if raw_type == "preprint" or src_type == "repository" or (venue_name and any(p in venue_name.lower() for p in ("arxiv", "biorxiv", "medrxiv", "ssrn", "research square"))):
            return PublicationClassification(
                source_id=source_id,
                title=title,
                authors=authors,
                doi=doi,
                arxiv_id=arxiv_id,
                venue_name=venue_name or "Preprint Repository",
                publication_year=pub_year,
                document_type="preprint",
                publication_status="PREPRINT",
                peer_review_status="PREPRINT",
                classification_evidence=f"OpenAlex indexes this work under preprint/repository source ({venue_name or 'Repository'}). OpenAlex indexing alone does not constitute peer review.",
                metadata_source="openalex",
                last_verified_date=now_str,
            )

        # Check conference proceedings
        if raw_type in ("proceedings-article", "proceedings") or src_type == "conference":
            return PublicationClassification(
                source_id=source_id,
                title=title,
                authors=authors,
                doi=doi,
                arxiv_id=arxiv_id,
                venue_name=venue_name or "Academic Conference Proceedings",
                publication_year=pub_year,
                document_type="proceedings-article",
                publication_status="PUBLISHED",
                peer_review_status="PEER_REVIEWED_CONFERENCE",
                classification_evidence=f"OpenAlex metadata identifies venue as conference proceedings ({venue_name or 'Conference'}).",
                metadata_source="openalex",
                last_verified_date=now_str,
            )

        # Check peer-reviewed journal: requires verified journal source type, DOAJ indexing, or recognized journal venue
        is_journal_venue = bool(venue_name and any(
            j_term in venue_name.lower()
            for j_term in ("journal", "transactions", "annals", "nature", "science", "letters", "review", "communications", "ieee", "acm", "springer", "elsevier")
        ))
        if raw_type in ("journal-article", "article") and (src_type == "journal" or is_in_doaj or is_journal_venue):
            evidence = f"Published in recognized scholarly journal '{venue_name or 'Scholarly Journal'}'"
            if is_in_doaj:
                evidence += " (Indexed in Directory of Open Access Journals - DOAJ)"
            return PublicationClassification(
                source_id=source_id,
                title=title,
                authors=authors,
                doi=doi,
                arxiv_id=arxiv_id,
                venue_name=venue_name or "Scholarly Journal",
                publication_year=pub_year,
                document_type="journal-article",
                publication_status="PUBLISHED",
                peer_review_status="PEER_REVIEWED_JOURNAL",
                classification_evidence=evidence,
                metadata_source="openalex",
                last_verified_date=now_str,
            )

        # Technical report / book / other
        if "report" in raw_type or "technical" in raw_type:
            return PublicationClassification(
                source_id=source_id,
                title=title,
                authors=authors,
                doi=doi,
                arxiv_id=arxiv_id,
                venue_name=venue_name or "Institutional Publisher",
                publication_year=pub_year,
                document_type="report",
                publication_status="PUBLISHED",
                peer_review_status="TECHNICAL_REPORT",
                classification_evidence="Document classified as technical report or working paper.",
                metadata_source="openalex",
                last_verified_date=now_str,
            )

        # Inconclusive metadata
        return PublicationClassification(
            source_id=source_id,
            title=title,
            authors=authors,
            doi=doi,
            arxiv_id=arxiv_id,
            venue_name=venue_name,
            publication_year=pub_year,
            document_type=raw_type or "unknown",
            publication_status="UNKNOWN",
            peer_review_status="UNKNOWN",
            classification_evidence="Metadata insufficient to confirm publication venue or peer-review status. OpenAlex index record lacks confirmed journal or conference editorial board validation.",
            metadata_source="openalex",
            last_verified_date=now_str,
        )

    def _classify_generic_work(
        self,
        source: Dict[str, Any],
        meta: Dict[str, Any],
        now_str: str,
    ) -> PublicationClassification:
        """Fallback classification when provider is unknown or metadata is scarce."""
        source_id = source.get("id", "generic_source")
        title = source.get("title", "")
        authors = source.get("authors", "")
        doi = source.get("doi")
        arxiv_id = source.get("arxiv_id")
        pub_year = source.get("publication_year")

        venue_name = source.get("venue") or meta.get("venue")

        if arxiv_id:
            return PublicationClassification(
                source_id=source_id,
                title=title,
                authors=authors,
                doi=doi,
                arxiv_id=arxiv_id,
                venue_name="arXiv",
                publication_year=pub_year,
                document_type="preprint",
                publication_status="PREPRINT",
                peer_review_status="PREPRINT",
                classification_evidence="arXiv identifier detected without verified external journal publication.",
                metadata_source="generic_fallback",
                last_verified_date=now_str,
            )

        return PublicationClassification(
            source_id=source_id,
            title=title,
            authors=authors,
            doi=doi,
            arxiv_id=arxiv_id,
            venue_name=venue_name,
            publication_year=pub_year,
            document_type="unknown",
            publication_status="UNKNOWN",
            peer_review_status="UNKNOWN",
            classification_evidence="Publication status cannot be established from available metadata. Venue and peer review unverified.",
            metadata_source="generic_fallback",
            last_verified_date=now_str,
        )

    async def _query_crossref(self, doi: str) -> Optional[Dict[str, Any]]:
        """Optional metadata verification via Crossref API."""
        if not doi or not doi.strip():
            return None
        clean_doi = doi.replace("https://doi.org/", "").strip()
        url = f"https://api.crossref.org/works/{clean_doi}"
        headers = {"User-Agent": f"AutonomousResearchAssistant/1.0 (mailto:{settings.OPENALEX_EMAIL})"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("message", {})
                    containers = data.get("container-title", [])
                    venue = containers[0] if containers else None
                    c_type = data.get("type", "")
                    return {"venue": venue, "type": c_type}
        except Exception as e:
            logger.debug("Crossref lookup skipped or timed out for DOI %s: %s", doi, e)

        return None
