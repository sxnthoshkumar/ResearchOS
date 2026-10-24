"""
Evidence Retrieval & Scholarly Source Pipeline.
Coordinates OpenAlex and arXiv search adapters, performs cross-source deduplication,
executes document extraction, and persists records to the SQLite evidence registry.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.database.repositories import EvidenceRepository, SourceRepository
from app.research.arxiv import ArXivAdapter
from app.research.document_extractor import DocumentExtractor
from app.research.openalex import OpenAlexAdapter

logger = logging.getLogger(__name__)


class EvidenceRetrievalPipeline:
    """Manages scholarly search, deduplication, full-text extraction, and evidence persistence."""

    def __init__(self):
        self.openalex = OpenAlexAdapter()
        self.arxiv = ArXivAdapter()

    async def execute_search(
        self,
        run_id: str,
        query: str,
        subquestion_id: Optional[str] = None,
        providers: Optional[List[str]] = None,
        max_sources_per_query: int = 5,
        is_demo: bool = False,
        publication_preference: str = "all",
        evidence_preference: str = "full_text_preferred",
    ) -> List[Dict[str, Any]]:
        """Harvest, deduplicate, and persist sources and passages for a query."""
        if not providers:
            providers = ["openalex", "arxiv"]

        harvested_sources: List[Dict[str, Any]] = []

        if is_demo:
            # Deterministic synthetic evidence clearly labeled as demonstration data
            demo_sources = self._generate_demo_sources(query, subquestion_id)
            for s in demo_sources:
                existing = SourceRepository.find_duplicate(
                    run_id, doi=s.get("doi"), arxiv_id=s.get("arxiv_id"), title=s["title"]
                )
                if not existing:
                    saved_source = SourceRepository.add(
                        run_id=run_id,
                        title=s["title"],
                        authors=s.get("authors"),
                        publication_year=s.get("publication_year"),
                        abstract=s.get("abstract"),
                        doi=s.get("doi"),
                        arxiv_id=s.get("arxiv_id"),
                        canonical_url=s.get("canonical_url"),
                        provider=s.get("provider", "demo"),
                        access_status=s.get("access_status", "abstract_only"),
                        doc_type=s.get("doc_type", "demo_synthesis"),
                        inspected_full_text=s.get("inspected_full_text", 0),
                        raw_metadata={"is_demo": True},
                    )
                    # Add passages
                    for p in s.get("passages", []):
                        EvidenceRepository.add_passage(
                            source_id=saved_source["id"],
                            run_id=run_id,
                            passage_text=p["text"],
                            page_number=p.get("page", 1),
                            extraction_method="demo_synthesis",
                            subquestion_id=subquestion_id,
                            relevance_score=1.0,
                        )
                    harvested_sources.append(saved_source)
            return harvested_sources

        # Real scholarly source retrieval
        candidates: List[Dict[str, Any]] = []
        if "openalex" in providers:
            try:
                oa_results = await self.openalex.search(query, limit=max_sources_per_query)
                candidates.extend(oa_results)
            except Exception as e:
                logger.warning("OpenAlex search exception: %s", e)

        if "arxiv" in providers:
            try:
                arxiv_results = await self.arxiv.search(query, limit=max_sources_per_query)
                candidates.extend(arxiv_results)
            except Exception as e:
                logger.warning("arXiv search exception: %s", e)

        # Filter or reorder candidates based on publication preference
        if publication_preference == "peer_reviewed_only":
            candidates = [
                c for c in candidates
                if c.get("provider") != "arxiv" and c.get("doc_type") != "preprint"
            ]
        elif publication_preference == "preprints_preferred":
            candidates.sort(
                key=lambda c: 0 if (c.get("provider") == "arxiv" or c.get("doc_type") == "preprint") else 1
            )

        # Deduplicate candidates across providers
        for item in candidates:
            existing = SourceRepository.find_duplicate(
                run_id=run_id,
                doi=item.get("doi"),
                arxiv_id=item.get("arxiv_id"),
                title=item.get("title"),
            )
            if existing:
                continue

            # Ingest passages based on evidence_preference
            passages: List[Dict[str, Any]] = []
            inspected_full = 0
            access_status = "metadata_only"

            if evidence_preference != "abstract_only" and item.get("pdf_url"):
                try:
                    pdf_passages = await DocumentExtractor.extract_from_pdf_url(item["pdf_url"])
                    if pdf_passages:
                        passages = pdf_passages
                        inspected_full = 1
                        access_status = "full_text_inspected"
                except Exception as e:
                    logger.debug("PDF extraction failed for %s: %s", item.get("pdf_url"), e)

            if not passages and evidence_preference != "full_text_required" and item.get("abstract"):
                try:
                    abstract_passages = DocumentExtractor.extract_from_abstract(item["abstract"])
                    if abstract_passages:
                        passages = abstract_passages
                        access_status = "abstract_only"
                except Exception as e:
                    logger.debug("Abstract extraction failed for %s: %s", item.get("title"), e)

            if evidence_preference == "full_text_required" and inspected_full == 0:
                logger.debug("Skipping source %s: strict full_text_required enabled but no PDF parsed.", item.get("title"))
                continue

            # Save newly discovered source with accurate provenance and inspection status
            saved_source = SourceRepository.add(
                run_id=run_id,
                title=item["title"],
                authors=item.get("authors"),
                publication_year=item.get("publication_year"),
                abstract=item.get("abstract"),
                doi=item.get("doi"),
                arxiv_id=item.get("arxiv_id"),
                canonical_url=item.get("canonical_url"),
                provider=item.get("provider", "openalex"),
                access_status=access_status,
                doc_type=item.get("doc_type", "article"),
                inspected_full_text=inspected_full,
                raw_metadata=item.get("raw_metadata"),
            )

            # Save extracted passages with explicit foreign key link to saved_source["id"]
            for p in passages:
                EvidenceRepository.add_passage(
                    source_id=saved_source["id"],
                    run_id=run_id,
                    passage_text=p["passage_text"],
                    page_number=p.get("page_number", 1),
                    extraction_method=p.get("extraction_method", "abstract"),
                    subquestion_id=subquestion_id,
                    relevance_score=1.0,
                )

            saved_source["passages_count"] = len(passages)
            harvested_sources.append(saved_source)

        return harvested_sources

    def _generate_demo_sources(self, query: str, subquestion_id: Optional[str]) -> List[Dict[str, Any]]:
        """Produces transparently labeled demonstration benchmark evidence."""
        return [
            {
                "title": "[DEMO BENCHMARK] Foundations of Retrieval-Augmented Generation vs Parameter Fine-Tuning",
                "authors": ["Dr. Eleanor Vance", "Marcus Chen"],
                "publication_year": 2024,
                "abstract": "This study analyzes the operational duality between parameter fine-tuning and non-parametric vector retrieval. We measure knowledge freshness, GPU training expenditures, inference token latencies, and hallucination propagation across standardized QA benchmarks.",
                "doi": "10.5555/demo.rag.2024.01",
                "arxiv_id": "demo.2401.0001",
                "canonical_url": "https://example.org/demo/rag-vs-finetuning",
                "provider": "demo",
                "access_status": "full_text_open",
                "doc_type": "demonstration_preprint",
                "inspected_full_text": 1,
                "passages": [
                    {
                        "page": 2,
                        "text": "RAG architectures query dynamic document indexes at inference time without modifying underlying neural network weights. This permits instantaneous updates to domain knowledge bases while retaining zero retraining compute requirements.",
                    },
                    {
                        "page": 4,
                        "text": "Parametric fine-tuning modifies neural network weights through gradient descent. While inference latency remains identical to standard forward passes without vector search overhead, retraining costs scale with parameter count and risk catastrophic forgetting of pre-training general reasoning capabilities.",
                    },
                ],
            },
            {
                "title": "[DEMO BENCHMARK] Empirical Trade-offs in Domain-Specific QA: LoRA and Dense Indexing",
                "authors": ["Sophia Al-Mansoor", "David K. Ross"],
                "publication_year": 2023,
                "abstract": "We evaluate hybrid systems combining Low-Rank Adaptation (LoRA) with dense semantic search on clinical and financial decision support corpora. Hybrid systems reduce hallucination rates by 42% compared to fine-tuning alone while cutting retrieval latency.",
                "doi": "10.5555/demo.hybrid.2023.08",
                "arxiv_id": "demo.2308.0002",
                "canonical_url": "https://example.org/demo/lora-dense-search",
                "provider": "demo",
                "access_status": "abstract_only",
                "doc_type": "demonstration_article",
                "inspected_full_text": 0,
                "passages": [
                    {
                        "page": 1,
                        "text": "Hybrid architectures integrating parameter-efficient adapters (such as LoRA) with dense vector retrieval mechanisms demonstrate superior domain-specific question answering accuracy on specialized clinical vocabularies compared to isolated RAG or isolated fine-tuning pipelines.",
                    },
                    {
                        "page": 1,
                        "text": "Retrieval-augmented models remain vulnerable to noise injection when irrelevant or distractor documents are retrieved by vector similarity search. In such cases, the generator often incorporates factual errors from the distractor context into the final output.",
                    },
                ],
            },
        ]
