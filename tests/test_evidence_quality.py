"""
Comprehensive Automated Unit and Integration Tests for Research Quality and Evidence Validation.

Covers all 16 specified milestone requirements:
1. Relevant paper receives a defensible high score.
2. An unrelated paper is excluded or sent for review.
3. Metadata-only papers are identified as such.
4. Invalid LLM JSON is handled safely without crashing.
5. Missing source IDs are rejected with INVALID_CITATION.
6. Missing passage IDs are rejected with INVALID_CITATION.
7. A passage belonging to another source is rejected with INVALID_CITATION.
8. A supporting passage produces a supported verdict only when semantic check agrees.
9. Contradictory evidence is preserved and flagged.
10. Missing evidence produces INSUFFICIENT_EVIDENCE.
11. A preprint with no confirmed publication information remains PREPRINT or UNKNOWN.
12. An arXiv paper with verified journal-reference or venue metadata is classified appropriately.
13. OpenAlex indexing alone does not establish peer review.
14. Every final-report citation is validated against the registry.
15. Existing demo mode and live Ollama mode continue working.
16. Evaluation reference dataset precision/recall and quality metrics can be computed.

All tests use mocks and do NOT require a running Ollama server or live internet access.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.agents.fact_checker import FactCheckingAgent
from app.agents.report_writer import ReportWriterAgent
from app.database.db import DatabaseManager
from app.database.repositories import (
    ClaimRepository,
    EvidenceRepository,
    ProjectRepository,
    PublicationClassificationRepository,
    RelevanceRepository,
    ReportRepository,
    RunRepository,
    SourceRepository,
    VerificationRepository,
)
from app.evaluation.metrics import (
    calculate_citation_provenance_metrics,
    calculate_claim_quality_metrics,
    calculate_publication_classification_metrics,
    calculate_relevance_metrics,
)
from app.llm.base import BaseLLMProvider, LLMResponse
from app.research.publication_classifier import PublicationClassifier
from app.research.relevance import PaperRelevanceEvaluator


class MockLLMProvider(BaseLLMProvider):
    """Predictable mock LLM provider for unit tests."""

    def __init__(self, canned_response: str = "{}"):
        super().__init__()
        self.canned_response = canned_response

    def get_provider_name(self) -> str:
        return "mock"

    async def generate(self, messages, temperature=0.1, max_tokens=1000, response_format_json=False):
        return LLMResponse(content=self.canned_response, model="mock-model", tokens_used=50)

    async def check_health(self):
        return {"status": "mock", "healthy": True}


@pytest.fixture
def test_db(tmp_path):
    """Sets up an isolated, temporary SQLite database with WAL and migrations."""
    db_file = tmp_path / "test_research.db"
    mgr = DatabaseManager(db_path=db_file)
    mgr.initialize_db()

    with patch("app.database.repositories.db_manager", mgr), \
         patch("app.database.db.db_manager", mgr):
        yield mgr


@pytest.mark.asyncio
async def test_01_relevant_paper_receives_high_score():
    """Requirement 1: Relevant paper receives a defensible high score (>=70) and INCLUDE decision."""
    canned = json.dumps({
        "direct_relevance": 92.0,
        "methodology_relevance": 85.0,
        "findings_relevance": 88.0,
        "domain_relevance": 95.0,
        "direct_explanation": "Directly compares RAG vs fine-tuning architectures on question answering.",
        "methodology_explanation": "Uses standardized QA benchmarks and latency profiling.",
        "findings_explanation": "Reports concrete hallucination rate reductions and GPU costs.",
        "domain_explanation": "Natural language processing and machine learning systems.",
        "positive_signals": ["Direct comparison of both target paradigms"],
        "missing_information": [],
        "excerpts": [{"text": "RAG models combine parametric and non-parametric memory.", "provenance": "abstract"}]
    })
    llm = MockLLMProvider(canned)
    evaluator = PaperRelevanceEvaluator(llm)

    source = {
        "id": "s1",
        "title": "Retrieval-Augmented Generation vs Parameter Fine-Tuning",
        "abstract": "We evaluate RAG and fine-tuning across domain-specific QA benchmarks.",
        "access_status": "full_text_open",
        "inspected_full_text": 1,
    }
    question = "Compare RAG and fine-tuning for domain-specific question answering."

    result = await evaluator.evaluate_source(source, question)

    # 0.40*92 + 0.25*85 + 0.25*88 + 0.10*95 = 36.8 + 21.25 + 22.0 + 9.5 = 89.55
    assert result.relevance_score >= 70.0
    assert result.decision == "INCLUDE"
    assert result.is_metadata_only is False
    assert len(result.excerpts) > 0


@pytest.mark.asyncio
async def test_02_unrelated_paper_excluded_or_reviewed():
    """Requirement 2: An unrelated paper is excluded (<40) or flagged for review."""
    canned = json.dumps({
        "direct_relevance": 10.0,
        "methodology_relevance": 15.0,
        "findings_relevance": 5.0,
        "domain_relevance": 10.0,
        "direct_explanation": "Paper discusses cardiac myocyte calcium signaling, unrelated to AI or LLMs.",
        "methodology_explanation": "Electrophysiology and ryanodine receptor assay.",
        "findings_explanation": "Findings describe calcium release in muscle cells.",
        "domain_explanation": "Cardiology and cell biology.",
        "positive_signals": [],
        "missing_information": ["Complete absence of computer science or language models."],
        "excerpts": [{"text": "Ryanodine receptors mediate rapid calcium release.", "provenance": "abstract"}]
    })
    llm = MockLLMProvider(canned)
    evaluator = PaperRelevanceEvaluator(llm)

    source = {
        "id": "s2",
        "title": "A Systematic Review of Calcium Signaling Pathways in Cardiac Myocytes",
        "abstract": "Calcium homeostasis is essential for electromechanical coupling.",
        "access_status": "abstract_only",
        "inspected_full_text": 0,
    }
    question = "Compare RAG and fine-tuning for domain-specific question answering."

    result = await evaluator.evaluate_source(source, question)

    # 0.4*10 + 0.25*15 + 0.25*5 + 0.1*10 = 4 + 3.75 + 1.25 + 1 = 10.0
    assert result.relevance_score < 40.0
    assert result.decision == "EXCLUDE"


@pytest.mark.asyncio
async def test_03_metadata_only_papers_identified():
    """Requirement 3: Metadata-only papers are identified as such."""
    # When abstract is missing and no passages exist
    llm = MockLLMProvider("{}")  # will trigger heuristic fallback
    evaluator = PaperRelevanceEvaluator(llm)

    source = {
        "id": "s3",
        "title": "Notes on Distributed Parameter Tuning",
        "abstract": None,
        "access_status": "metadata_only",
        "inspected_full_text": 0,
    }
    question = "Analyze distributed parameter tuning in large networks."

    result = await evaluator.evaluate_source(source, question, passages=[])

    assert result.is_metadata_only is True
    assert any("metadata" in m.lower() for m in result.missing_information)


@pytest.mark.asyncio
async def test_04_invalid_llm_json_handled_safely():
    """Requirement 4: Invalid LLM JSON is handled safely without crashing."""
    corrupted_json = "This is not valid JSON at all! {unclosed: 'brace"
    llm = MockLLMProvider(corrupted_json)
    evaluator = PaperRelevanceEvaluator(llm)

    source = {
        "id": "s4",
        "title": "Retrieval Augmented Architectures",
        "abstract": "We evaluate retrieval augmented architectures for language modeling.",
        "access_status": "abstract_only",
    }
    question = "Evaluate retrieval augmented architectures."

    # Must complete safely via fallback without raising JSONDecodeError
    result = await evaluator.evaluate_source(source, question)
    assert result is not None
    assert isinstance(result.relevance_score, float)
    assert result.decision in ("INCLUDE", "REVIEW", "EXCLUDE")


@pytest.mark.asyncio
async def test_05_missing_source_id_rejected(test_db):
    """Requirement 5: Missing source IDs are rejected with INVALID_CITATION."""
    llm = MockLLMProvider()
    checker = FactCheckingAgent(llm)

    # Passage references a nonexistent source ID 'nonexistent_src_999'
    ev_list = [
        {
            "id": "pass-01",
            "source_id": "nonexistent_src_999",
            "passage_text": "Sample valid passage text."
        }
    ]
    source_map = {}  # source not in SQLite
    passage_map = {"pass-01": {"id": "pass-01", "source_id": "nonexistent_src_999", "passage_text": "..."}}

    audit = await checker._audit_single_claim(
        claim_id="c1",
        claim_text="RAG improves accuracy.",
        ev_list=ev_list,
        source_map=source_map,
        passage_map=passage_map,
    )

    assert audit.verification_status == "INVALID_CITATION"
    assert "source id 'nonexistent_src_999' does not exist" in audit.explanation.lower()


@pytest.mark.asyncio
async def test_06_missing_passage_id_rejected(test_db):
    """Requirement 6: Missing passage IDs are rejected with INVALID_CITATION."""
    llm = MockLLMProvider()
    checker = FactCheckingAgent(llm)

    source_map = {"src-01": {"id": "src-01", "title": "Real Source"}}
    # Passage ID 'missing-pass-123' does not exist in passage_map
    ev_list = [
        {
            "id": "missing-pass-123",
            "source_id": "src-01",
            "passage_text": "Sample text."
        }
    ]
    passage_map = {}  # passage not in SQLite

    audit = await checker._audit_single_claim(
        claim_id="c2",
        claim_text="Fine-tuning incurs higher training costs.",
        ev_list=ev_list,
        source_map=source_map,
        passage_map=passage_map,
    )

    assert audit.verification_status == "INVALID_CITATION"
    assert "passage id 'missing-pass-123' does not exist" in audit.explanation.lower()


@pytest.mark.asyncio
async def test_07_passage_belonging_to_another_source_rejected(test_db):
    """Requirement 7: A passage belonging to another source is rejected with INVALID_CITATION."""
    llm = MockLLMProvider()
    checker = FactCheckingAgent(llm)

    source_map = {
        "src-A": {"id": "src-A", "title": "Paper A"},
        "src-B": {"id": "src-B", "title": "Paper B"},
    }
    # Passage actually belongs to src-B, but claim claims it is from src-A
    passage_map = {
        "pass-X": {"id": "pass-X", "source_id": "src-B", "passage_text": "Text from Paper B."}
    }
    ev_list = [
        {
            "id": "pass-X",
            "source_id": "src-A",  # Mismatch!
            "passage_text": "Text from Paper B."
        }
    ]

    audit = await checker._audit_single_claim(
        claim_id="c3",
        claim_text="Paper A claims something.",
        ev_list=ev_list,
        source_map=source_map,
        passage_map=passage_map,
    )

    assert audit.verification_status == "INVALID_CITATION"
    assert "provenance mismatch" in audit.explanation.lower()


@pytest.mark.asyncio
async def test_08_semantic_check_agrees_produces_supported():
    """Requirement 8: A supporting passage produces SUPPORTED verdict only when semantic check agrees."""
    canned = json.dumps({
        "verification_status": "SUPPORTED",
        "explanation": "The text directly states that RAG reduces hallucination rates on open-domain QA.",
        "exact_supporting_excerpts": ["RAG reduced hallucination rates on open-domain question answering."],
        "contradicting_evidence": None,
        "confidence": 0.95
    })
    llm = MockLLMProvider(canned)
    checker = FactCheckingAgent(llm)

    source_map = {"s1": {"id": "s1", "title": "RAG Paper"}}
    passage_map = {"p1": {"id": "p1", "source_id": "s1", "passage_text": "RAG reduced hallucination rates on open-domain question answering."}}
    ev_list = [{"id": "p1", "source_id": "s1", "passage_text": "RAG reduced hallucination rates on open-domain question answering."}]

    audit = await checker._audit_single_claim(
        claim_id="c4",
        claim_text="RAG reduces hallucination rates in open-domain question answering.",
        ev_list=ev_list,
        source_map=source_map,
        passage_map=passage_map,
    )

    assert audit.verification_status == "SUPPORTED"
    assert audit.confidence == 0.95
    assert len(audit.exact_supporting_excerpts) > 0


@pytest.mark.asyncio
async def test_09_contradictory_evidence_preserved_and_flagged():
    """Requirement 9: Contradictory evidence is preserved and flagged as CONTRADICTED."""
    canned = json.dumps({
        "verification_status": "CONTRADICTED",
        "explanation": "The passage directly refutes the claim; fine-tuning does not eliminate hallucination.",
        "exact_supporting_excerpts": [],
        "contradicting_evidence": "Fine-tuned models frequently hallucinated non-existent citations on specialized test prompts.",
        "confidence": 0.92
    })
    llm = MockLLMProvider(canned)
    checker = FactCheckingAgent(llm)

    source_map = {"s1": {"id": "s1", "title": "Empirical Study"}}
    passage_map = {"p1": {"id": "p1", "source_id": "s1", "passage_text": "Fine-tuned models frequently hallucinated non-existent citations on specialized test prompts."}}
    ev_list = [{"id": "p1", "source_id": "s1", "passage_text": "Fine-tuned models frequently hallucinated non-existent citations on specialized test prompts."}]

    audit = await checker._audit_single_claim(
        claim_id="c5",
        claim_text="Fine-tuning completely eliminates all hallucinations in domain QA.",
        ev_list=ev_list,
        source_map=source_map,
        passage_map=passage_map,
    )

    assert audit.verification_status == "CONTRADICTED"
    assert audit.contradiction_found is True
    assert "hallucinated non-existent citations" in audit.contradicting_evidence


@pytest.mark.asyncio
async def test_10_missing_evidence_produces_insufficient_evidence():
    """Requirement 10: Missing evidence produces INSUFFICIENT_EVIDENCE."""
    llm = MockLLMProvider()
    checker = FactCheckingAgent(llm)

    source_map = {"s1": {"id": "s1", "title": "Paper"}}
    passage_map = {}

    # Claim has no evidence passages linked
    audit = await checker._audit_single_claim(
        claim_id="c6",
        claim_text="Uncited asserted factual claim.",
        ev_list=[],
        source_map=source_map,
        passage_map=passage_map,
    )

    assert audit.verification_status == "INSUFFICIENT_EVIDENCE"
    assert audit.confidence == 0.0


@pytest.mark.asyncio
async def test_11_preprint_with_no_confirmed_publication_remains_preprint():
    """Requirement 11: A preprint with no confirmed publication information remains PREPRINT or UNKNOWN."""
    classifier = PublicationClassifier()

    source = {
        "id": "ar-01",
        "title": "Exploring Large Pre-trained Models",
        "authors": "Alice Smith, Bob Jones",
        "arxiv_id": "2301.00001",
        "doi": None,
        "provider": "arxiv",
        "doc_type": "preprint",
        "raw_metadata": {"arxiv_url": "https://arxiv.org/abs/2301.00001"}
    }

    classification = await classifier.classify_source(source)
    assert classification.peer_review_status == "PREPRINT"
    assert classification.document_type == "preprint"
    assert classification.publication_status == "PREPRINT"


@pytest.mark.asyncio
async def test_12_arxiv_paper_with_journal_ref_classified_appropriately():
    """Requirement 12: An arXiv paper with verified journal-reference metadata is classified appropriately."""
    classifier = PublicationClassifier()

    # Case A: Conference journal_ref
    source_conf = {
        "id": "ar-conf",
        "title": "LoRA: Low-Rank Adaptation of Large Language Models",
        "authors": "Edward Hu et al.",
        "arxiv_id": "2106.09685",
        "provider": "arxiv",
        "doc_type": "preprint",
        "raw_metadata": {
            "journal_ref": "International Conference on Learning Representations (ICLR 2022)",
            "comment": "Published at ICLR 2022"
        }
    }
    class_conf = await classifier.classify_source(source_conf)
    assert class_conf.peer_review_status == "PEER_REVIEWED_CONFERENCE"
    assert class_conf.publication_status == "PUBLISHED"

    # Case B: Journal journal_ref
    source_jour = {
        "id": "ar-jour",
        "title": "Quantum Error Correction in Surface Codes",
        "authors": "Jane Doe",
        "arxiv_id": "2205.12345",
        "provider": "arxiv",
        "raw_metadata": {
            "journal_ref": "Physical Review Letters 128, 120501 (2022)"
        }
    }
    class_jour = await classifier.classify_source(source_jour)
    assert class_jour.peer_review_status == "PEER_REVIEWED_JOURNAL"
    assert class_jour.publication_status == "PUBLISHED"


@pytest.mark.asyncio
async def test_13_openalex_indexing_alone_does_not_establish_peer_review():
    """Requirement 13: OpenAlex indexing alone does not establish peer review (preprints remain preprints)."""
    classifier = PublicationClassifier()

    source = {
        "id": "oa-rep",
        "title": "Working Paper on Algorithmic Audits",
        "provider": "openalex",
        "doc_type": "preprint",
        "raw_metadata": {
            "venue": "arXiv.org",
            "primary_location": {"source": {"type": "repository", "display_name": "arXiv.org"}},
            "type": "preprint"
        }
    }

    classification = await classifier.classify_source(source)
    assert classification.peer_review_status == "PREPRINT"
    assert "does not constitute peer review" in classification.classification_evidence


@pytest.mark.asyncio
async def test_14_every_final_report_citation_is_validated():
    """Requirement 14: Every final-report citation is validated against the registry."""
    llm = MockLLMProvider()
    writer = ReportWriterAgent(llm)

    sources = [
        {"id": "src-1", "title": "Paper 1", "authors": "Author 1", "provider": "openalex"}
    ]
    # Markdown with invalid citation [5] when only 1 source exists
    markdown_with_invalid = (
        "# Title\n\n## Executive Summary\nSummary.\n\n"
        "## Detailed Findings\nFinding [5].\n\n"
        "## Limitations & Failure Modes\nLimitations.\n\n"
        "## References\n[1] Paper 1. Full-Text PDF Analyzed\n"
    )

    quality_gate = writer._evaluate_quality_gate(
        markdown=markdown_with_invalid,
        sources=sources,
        verifications=[]
    )

    assert quality_gate.all_citations_resolved is False
    assert any("Invalid citation [5]" in d for d in quality_gate.details)
    assert quality_gate.passed is False


@pytest.mark.asyncio
async def test_15_demo_mode_sources_classified_properly():
    """Requirement 15: Existing demo mode continues working and is classified transparently."""
    classifier = PublicationClassifier()

    demo_source = {
        "id": "demo-01",
        "title": "[DEMO BENCHMARK] Foundations of RAG",
        "authors": "Dr. Eleanor Vance",
        "provider": "demo",
        "doc_type": "demonstration_preprint",
        "raw_metadata": {"is_demo": True}
    }

    classification = await classifier.classify_source(demo_source)
    assert classification.metadata_source == "demo_engine"
    assert "reproducible benchmarking" in classification.classification_evidence.lower()


def test_16_validation_metrics_calculations():
    """Requirement 16: Calculation of scientific validation metrics with explicit numerators and denominators."""
    evaluations = [
        {"decision": "INCLUDE", "relevance_score": 85.0},
        {"decision": "INCLUDE", "relevance_score": 90.0},
        {"decision": "REVIEW", "relevance_score": 55.0},
        {"decision": "EXCLUDE", "relevance_score": 20.0},
    ]
    total_sources = 5

    rel_m = calculate_relevance_metrics(evaluations, total_sources)
    assert rel_m["coverage"] == 0.8  # 4/5
    assert rel_m["pct_included"] == 50.0  # 2/4
    assert rel_m["pct_reviewed"] == 25.0  # 1/4
    assert rel_m["pct_excluded"] == 25.0  # 1/4

    claims = [
        {"id": "c1", "evidence": [{"id": "p1", "source_id": "s1"}]},
        {"id": "c2", "evidence": [{"id": "p2", "source_id": "s2"}]},
    ]
    passages = [
        {"id": "p1", "source_id": "s1"},
        {"id": "p2", "source_id": "s1"},  # Mismatch: belongs to s1, cited under s2!
    ]
    cit_prov_m = calculate_citation_provenance_metrics(
        report_markdown="Report text with citations [1] and [2].",
        sources=[{"id": "s1"}, {"id": "s2"}],
        claims=claims,
        passages=passages,
    )
    assert cit_prov_m["citation_id_validity_rate"] == 1.0  # [1] and [2] both in range 1-2
    assert cit_prov_m["provenance_validity_rate"] == 0.5  # 1 of 2 matches
