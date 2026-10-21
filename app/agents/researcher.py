"""
Agent 2: Research Agent.
Executes targeted scholarly retrieval across OpenAlex and arXiv according to the research plan,
performs deduplication, extracts text passages, and populates the SQLite evidence registry.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from app.agents.planner import ResearchPlan
from app.database.repositories import (
    EvidenceRepository,
    PublicationClassificationRepository,
    RelevanceRepository,
    SourceRepository,
)
from app.llm import get_llm_provider
from app.llm.base import BaseLLMProvider
from app.research.evidence_retrieval import EvidenceRetrievalPipeline
from app.research.publication_classifier import PublicationClassifier
from app.research.relevance import PaperRelevanceEvaluator

logger = logging.getLogger(__name__)


class SubquestionHarvest(BaseModel):
    subquestion_id: str
    query_executed: str
    sources_found: int
    passages_stored: int


class ResearchHarvestResult(BaseModel):
    run_id: str
    total_sources: int
    total_passages: int
    open_access_count: int
    inspected_full_text_count: int
    included_count: int = 0
    reviewed_count: int = 0
    excluded_count: int = 0
    subquestion_harvests: List[SubquestionHarvest]
    unresolved_gaps: List[str]


class ResearchAgent:
    """Automates scholarly source retrieval, normalization, relevance evaluation, and classification."""

    def __init__(
        self,
        pipeline: Optional[EvidenceRetrievalPipeline] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
    ):
        self.pipeline = pipeline or EvidenceRetrievalPipeline()
        self.llm = llm_provider or get_llm_provider(force_demo=True)
        self.relevance_evaluator = PaperRelevanceEvaluator(self.llm)
        self.publication_classifier = PublicationClassifier()

    async def execute_plan(
        self,
        run_id: str,
        plan: ResearchPlan,
        search_providers: Optional[List[str]] = None,
        max_sources: int = 10,
        is_demo: bool = False,
    ) -> ResearchHarvestResult:
        """Executes targeted searches for each subquestion in the research plan."""
        harvest_log: List[SubquestionHarvest] = []
        providers = search_providers or ["openalex", "arxiv"]
        unresolved_gaps: List[str] = []

        total_collected = 0

        for sq in plan.subquestions:
            if total_collected >= max_sources:
                logger.info("Reached maximum sources cap (%s). Stopping retrieval.", max_sources)
                break

            sq_sources_count = 0
            sq_passages_count = 0
            primary_query = sq.search_queries[0] if sq.search_queries else plan.research_question

            try:
                sources = await self.pipeline.execute_search(
                    run_id=run_id,
                    query=primary_query,
                    subquestion_id=sq.id,
                    providers=providers,
                    max_sources_per_query=max(2, max_sources // len(plan.subquestions)),
                    is_demo=is_demo,
                )
                sq_sources_count = len(sources)
                total_collected += sq_sources_count

                # Count passages saved for this subquestion
                passages = EvidenceRepository.list_by_run(run_id)
                sq_passages_count = len([p for p in passages if p.get("subquestion_id") == sq.id])

            except Exception as e:
                logger.error("Error harvesting for subquestion %s: %s", sq.id, e)
                unresolved_gaps.append(f"Retrieval error for subquestion '{sq.title}': {e}")

            if sq_sources_count == 0:
                unresolved_gaps.append(f"No empirical sources discovered for subquestion: '{sq.title}'")

            harvest_log.append(
                SubquestionHarvest(
                    subquestion_id=sq.id,
                    query_executed=primary_query,
                    sources_found=sq_sources_count,
                    passages_stored=sq_passages_count,
                )
            )

        # Retrieve cumulative stats from repository
        all_sources = SourceRepository.list_by_run(run_id)
        all_passages = EvidenceRepository.list_by_run(run_id)
        oa_count = sum(1 for s in all_sources if s.get("access_status") == "full_text_open")
        full_text_inspected = sum(1 for s in all_sources if s.get("inspected_full_text") == 1)

        # Evaluate Relevance & Publication Classification for every retrieved source
        included_c = 0
        reviewed_c = 0
        excluded_c = 0

        for s in all_sources:
            s_passages = EvidenceRepository.list_by_source(s["id"])
            try:
                # 1. Relevance Evaluation
                rel_res = await self.relevance_evaluator.evaluate_source(
                    source=s,
                    research_question=plan.research_question,
                    passages=s_passages,
                )
                RelevanceRepository.record(
                    source_id=s["id"],
                    run_id=run_id,
                    research_question=plan.research_question,
                    relevance_score=rel_res.relevance_score,
                    direct_relevance=rel_res.direct_relevance,
                    methodology_relevance=rel_res.methodology_relevance,
                    findings_relevance=rel_res.findings_relevance,
                    domain_relevance=rel_res.domain_relevance,
                    direct_explanation=rel_res.direct_explanation,
                    methodology_explanation=rel_res.methodology_explanation,
                    findings_explanation=rel_res.findings_explanation,
                    domain_explanation=rel_res.domain_explanation,
                    decision=rel_res.decision,
                    is_metadata_only=rel_res.is_metadata_only,
                    positive_signals=rel_res.positive_signals,
                    missing_information=rel_res.missing_information,
                    excerpts=[e.model_dump() for e in rel_res.excerpts],
                )

                if rel_res.decision == "INCLUDE":
                    included_c += 1
                elif rel_res.decision == "REVIEW":
                    reviewed_c += 1
                else:
                    excluded_c += 1

            except Exception as e:
                logger.error("Relevance evaluation failed for source %s: %s", s.get("id"), e)
                # Fallback to REVIEW when evaluation fails
                RelevanceRepository.record(
                    source_id=s["id"],
                    run_id=run_id,
                    research_question=plan.research_question,
                    relevance_score=50.0,
                    direct_relevance=50.0,
                    methodology_relevance=50.0,
                    findings_relevance=50.0,
                    domain_relevance=50.0,
                    decision="REVIEW",
                    direct_explanation="Automated relevance evaluation encountered an exception; flagged for review.",
                )
                reviewed_c += 1

            try:
                # 2. Publication & Peer-Review Classification
                pub_class = await self.publication_classifier.classify_source(
                    source=s,
                    raw_metadata=s.get("raw_metadata"),
                )
                PublicationClassificationRepository.record(
                    source_id=s["id"],
                    run_id=run_id,
                    venue_name=pub_class.venue_name,
                    document_type=pub_class.document_type,
                    publication_status=pub_class.publication_status,
                    peer_review_status=pub_class.peer_review_status,
                    classification_evidence=pub_class.classification_evidence,
                    metadata_source=pub_class.metadata_source,
                    last_verified_date=pub_class.last_verified_date,
                )
            except Exception as e:
                logger.error("Publication classification failed for source %s: %s", s.get("id"), e)
                PublicationClassificationRepository.record(
                    source_id=s["id"],
                    run_id=run_id,
                    peer_review_status="UNKNOWN",
                    classification_evidence=f"Automated classification exception: {e}",
                    metadata_source="fallback",
                )

        return ResearchHarvestResult(
            run_id=run_id,
            total_sources=len(all_sources),
            total_passages=len(all_passages),
            open_access_count=oa_count,
            inspected_full_text_count=full_text_inspected,
            included_count=included_c,
            reviewed_count=reviewed_c,
            excluded_count=excluded_c,
            subquestion_harvests=harvest_log,
            unresolved_gaps=unresolved_gaps,
        )
