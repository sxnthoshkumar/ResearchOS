"""
Regression Test Suite for Research Integrity Audit.
Tests covering:
1. Rejection of figure/table captions, layout artifacts, author lists, and dataset Q&A items.
2. Strict heuristic confidence bounds per verdict (preventing high confidence for insufficient evidence).
3. Mismatched DOI/metadata and invalid foreign key / provenance rejections.
4. Filtering of lexically similar but irrelevant papers (e.g., cosmology fine-tuning).
5. Comprehensive four-facet report synthesis (factual accuracy, knowledge freshness, computational cost, limitations).
"""

import pytest
from app.agents.analyst import AnalysisAgent
from app.agents.fact_checker import FactCheckingAgent
from app.agents.report_writer import ReportWriterAgent
from app.llm.base import BaseLLMProvider, LLMResponse
from app.research.relevance import PaperRelevanceEvaluator


class MockLLM(BaseLLMProvider):
    def get_provider_name(self) -> str:
        return "mock"

    async def generate(self, messages, temperature=0.7, response_format_json=False):
        return LLMResponse(content="{}", model="mock", total_tokens=10)


# =====================================================================
# 1. Claim Filtering Tests (Figure Captions, Dataset Artifacts, etc.)
# =====================================================================

def test_figure_and_table_captions_rejected():
    """Figure and table captions from PDF layouts must not be accepted as academic claims."""
    captions = [
        "Figure 2: Example of a document from Washington state present in our dataset.",
        "Figure 1: Methodology pipeline. Domain-specific datasets are collected.",
        "Table 1: An example question from Entailment Bank and associated factoids.",
        "Fig. 4. Overview of the storage and retrieval architecture.",
        "Example of a document from Washington state present in our dataset.",
        "Methodology pipeline shown in Figure 3.",
    ]
    for cap in captions:
        assert not AnalysisAgent._is_valid_academic_claim(cap), f"Failed to reject caption/artifact: {cap}"


def test_dataset_sample_qa_prompts_rejected():
    """Raw dataset queries, prompts, and sample answers must not be accepted as research claims."""
    sample_queries = [
        "State What is the best times to plant trees and shrubs in ? GPT-4 answers Arkansas The best time to plant trees and shrubs in Arkansas is during the fall and early spring seasons.",
        "What is the best times to plant trees and shrubs in Arkansas?",
        "Question: How might eruptions affect plants? Answer: Eruptions emit lava.",
        "Prompt: Summarize the litigation history of medical malpractice.",
    ]
    for q in sample_queries:
        assert not AnalysisAgent._is_valid_academic_claim(q), f"Failed to reject sample Q&A: {q}"


def test_sentence_fragments_and_author_headers_rejected():
    """Incomplete noun phrases and author metadata banners must be rejected."""
    invalids = [
        "data processing and decision-making processes.",
        "RAG VS FINE-TUNING: PIPELINES, TRADEOFFS, AND A CASE STUDY ON AGRICULTURE Microsoft Angels Balaguer, Vinamra Benara, Renato Cunha",
        "Short text.",
        "A b c d.",
    ]
    for inv in invalids:
        assert not AnalysisAgent._is_valid_academic_claim(inv), f"Failed to reject invalid fragment/banner: {inv}"


def test_valid_analytical_claims_accepted():
    """Complete, grammatically sound analytical claims must be accepted."""
    valid_claims = [
        "RAG augments the prompt with external data, while fine-tuning incorporates knowledge into model weights.",
        "Fine-tuning yields an accuracy increase of 6 percentage points, while adding RAG provides an additional 5 percentage points.",
        "RAG provides dynamic knowledge freshness without retraining, but incurs retrieval latency and vector database infrastructure costs.",
        "Fine-tuning models on domain-specific datasets significantly reduces inference latency compared to multi-hop retrieval pipelines.",
    ]
    for vc in valid_claims:
        assert AnalysisAgent._is_valid_academic_claim(vc), f"Rejected valid academic claim: {vc}"


# =====================================================================
# 2. Heuristic Evidentiary Confidence Bounding Tests
# =====================================================================

@pytest.mark.asyncio
async def test_insufficient_evidence_confidence_ceiling():
    """Claims with INSUFFICIENT_EVIDENCE must never receive high confidence even if model outputs 0.85 or 0.95."""
    class InsufficientEvidenceLLM(MockLLM):
        async def generate(self, messages, temperature=0.7, response_format_json=False):
            # Model hallucinating high confidence on insufficient evidence
            return LLMResponse(
                content='{"verification_status": "INSUFFICIENT_EVIDENCE", "explanation": "No textual passage verifies this statement.", "exact_supporting_excerpts": [], "confidence": 0.85}',
                model="mock",
                total_tokens=20,
            )

    agent = FactCheckingAgent(InsufficientEvidenceLLM())
    record = await agent._evaluate_semantic_entailment(
        claim_id="c-1",
        claim_text="Figure 2: Example of a document from Washington state present in our dataset.",
        source_ids=["s-1"],
        passage_ids=["p-1"],
        evidence_list=[{"id": "p-1", "source_id": "s-1", "passage_text": "General discussion of PDF layouts."}],
        is_direct_quote=False,
    )
    assert record.verification_status == "INSUFFICIENT_EVIDENCE"
    # Must be bounded strictly <= 0.15, NEVER 0.85
    assert record.confidence <= 0.15, f"Confidence was {record.confidence}, expected <= 0.15"


@pytest.mark.asyncio
async def test_partially_supported_confidence_ceiling():
    """Claims with PARTIALLY_SUPPORTED must never exceed 0.60 even if model outputs 0.95."""
    class PartialSupportLLM(MockLLM):
        async def generate(self, messages, temperature=0.7, response_format_json=False):
            return LLMResponse(
                content='{"verification_status": "PARTIALLY_SUPPORTED", "explanation": "Passage partially aligns but overstates generalizability.", "exact_supporting_excerpts": ["some partial text"], "confidence": 0.95}',
                model="mock",
                total_tokens=20,
            )

    agent = FactCheckingAgent(PartialSupportLLM())
    record = await agent._evaluate_semantic_entailment(
        claim_id="c-2",
        claim_text="RAG is always faster and cheaper than any fine-tuned model across all enterprise workloads.",
        source_ids=["s-1"],
        passage_ids=["p-1"],
        evidence_list=[{"id": "p-1", "source_id": "s-1", "passage_text": "RAG shows latency tradeoffs in specific query setups."}],
        is_direct_quote=False,
    )
    assert record.verification_status == "PARTIALLY_SUPPORTED"
    # Must be bounded strictly <= 0.60, NEVER 0.95
    assert record.confidence <= 0.60, f"Confidence was {record.confidence}, expected <= 0.60"


@pytest.mark.asyncio
async def test_contradicted_support_score_zero():
    """Claims with CONTRADICTED status must receive 0.0 support confidence."""
    class ContradictedLLM(MockLLM):
        async def generate(self, messages, temperature=0.7, response_format_json=False):
            return LLMResponse(
                content='{"verification_status": "CONTRADICTED", "explanation": "Directly refutes the claim.", "contradicting_evidence": "Text explicitly says RAG is slower.", "exact_supporting_excerpts": [], "confidence": 0.90}',
                model="mock",
                total_tokens=20,
            )

    agent = FactCheckingAgent(ContradictedLLM())
    record = await agent._evaluate_semantic_entailment(
        claim_id="c-3",
        claim_text="RAG requires zero runtime compute and has zero inference latency.",
        source_ids=["s-1"],
        passage_ids=["p-1"],
        evidence_list=[{"id": "p-1", "source_id": "s-1", "passage_text": "Text explicitly says RAG is slower and incurs runtime vector search overhead."}],
        is_direct_quote=False,
    )
    assert record.verification_status == "CONTRADICTED"
    assert record.confidence == 0.0, f"Confidence was {record.confidence}, expected 0.0"


# =====================================================================
# 3. Provenance and Foreign Key Integrity Tests
# =====================================================================

@pytest.mark.asyncio
async def test_mismatched_provenance_rejected():
    """A claim citing a passage that belongs to a different source must fail with INVALID_CITATION."""
    agent = FactCheckingAgent(MockLLM())
    source_map = {"s-1": {"id": "s-1", "title": "Source 1"}}
    passage_map = {"p-1": {"id": "p-1", "source_id": "s-OTHER", "passage_text": "Text"}}

    record = await agent._audit_single_claim(
        claim_id="c-4",
        claim_text="Some valid claim text for checking provenance.",
        ev_list=[{"id": "p-1", "source_id": "s-1"}],
        source_map=source_map,
        passage_map=passage_map,
    )
    assert record.verification_status == "INVALID_CITATION"
    assert "Provenance mismatch" in record.explanation
    assert record.confidence == 0.0


@pytest.mark.asyncio
async def test_nonexistent_source_rejected():
    """A claim citing a nonexistent source ID must fail with INVALID_CITATION."""
    agent = FactCheckingAgent(MockLLM())
    source_map = {}
    passage_map = {"p-1": {"id": "p-1", "source_id": "s-nonexistent", "passage_text": "Text"}}

    record = await agent._audit_single_claim(
        claim_id="c-5",
        claim_text="Some valid claim text for checking source lookup.",
        ev_list=[{"id": "p-1", "source_id": "s-nonexistent"}],
        source_map=source_map,
        passage_map=passage_map,
    )
    assert record.verification_status == "INVALID_CITATION"
    assert record.confidence == 0.0


# =====================================================================
# 4. Lexical Similarity vs. Semantic Relevance Filtering
# =====================================================================

@pytest.mark.asyncio
async def test_lexically_similar_irrelevant_paper_filtered():
    """A cosmology paper matching 'fine tuned' must not be classified as direct evidence for RAG vs Fine-tuning."""
    evaluator = PaperRelevanceEvaluator(MockLLM())
    source = {
        "id": "s-cosmo",
        "title": "Is The Universal Matter - Antimatter Asymmetry Fine Tuned?",
        "abstract": "We analyze the cosmological baryon asymmetry and whether parameters of the early universe require fine tuning.",
        "canonical_url": "http://arxiv.org/abs/1801.10059v1",
        "doc_type": "preprint",
    }
    question = "Compare retrieval-augmented generation (RAG) and fine-tuning for domain-specific question answering, focusing on factual accuracy, knowledge freshness, computational cost, and limitations."
    result = await evaluator.evaluate_source(source, question)
    assert result.decision in ("REVIEW", "EXCLUDE")
    assert result.evidence_role in ("BACKGROUND_CONTEXT", "IRRELEVANT")
    assert result.direct_relevance <= 55.0


# =====================================================================
# 5. Four-Facet Report Synthesis Tests
# =====================================================================

def test_fallback_report_structure_covers_all_four_facets():
    """The fallback report structure must explicitly cover accuracy, freshness, cost, and limitations."""
    writer = ReportWriterAgent(MockLLM())
    question = "Compare retrieval-augmented generation (RAG) and fine-tuning for domain-specific question answering, focusing on factual accuracy, knowledge freshness, computational cost, and limitations."
    structure = writer._generate_fallback_report_structure(question, [], {"s-1": 1, "s-2": 2})

    headings = [sec["heading"].lower() for sec in structure["findings_sections"]]
    assert any("accuracy" in h for h in headings), "Missing factual accuracy section"
    assert any("freshness" in h for h in headings), "Missing knowledge freshness section"
    assert any("cost" in h for h in headings), "Missing computational cost section"
    assert any("limitation" in h for h in headings), "Missing limitations section"

    table = structure.get("comparison_table", {})
    assert "headers" in table
    assert len(table.get("rows", [])) >= 4
    for row in table["rows"]:
        assert len(row) == 3
        assert "..." not in row
