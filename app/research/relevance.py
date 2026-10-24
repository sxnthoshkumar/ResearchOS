"""
Paper Relevance Evaluation Module.
Evaluates retrieved scholarly sources against the original research question.

HEURISTIC DOCUMENTATION:
The component weights:
- Direct relevance: 40% (0.40)
- Methodology relevance: 25% (0.25)
- Findings relevance: 25% (0.25)
- Domain relevance: 10% (0.10)
and the decision thresholds:
- 70-100: INCLUDE
- 40-69: REVIEW
- 0-39: EXCLUDE
are operational heuristics designed to prevent irrelevant literature contamination in downstream
academic synthesis. They are NOT empirically validated universal constants. Thresholds and weights
can be adjusted depending on research precision/recall preferences.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.llm.base import BaseLLMProvider, LLMMessage
from app.llm.json_repair import extract_structured_json

logger = logging.getLogger(__name__)

# Configurable heuristic defaults
DEFAULT_DIRECT_WEIGHT = 0.40
DEFAULT_METHODOLOGY_WEIGHT = 0.25
DEFAULT_FINDINGS_WEIGHT = 0.25
DEFAULT_DOMAIN_WEIGHT = 0.10

DEFAULT_INCLUDE_THRESHOLD = 70.0
DEFAULT_REVIEW_THRESHOLD = 40.0


class RelevanceExcerpt(BaseModel):
    text: str
    provenance: str  # e.g., "title", "abstract", "passage:page_2"


class StructuredRelevanceResult(BaseModel):
    source_id: str
    research_question: str
    relevance_score: float  # Deterministically computed weighted score (0-100)
    direct_relevance: float  # 0-100
    methodology_relevance: float  # 0-100
    findings_relevance: float  # 0-100
    domain_relevance: float  # 0-100
    evidence_role: str = "DIRECT_EVIDENCE"  # DIRECT_EVIDENCE, BACKGROUND_CONTEXT, IRRELEVANT
    facet_coverage: Dict[str, bool] = Field(default_factory=dict)
    direct_explanation: str
    methodology_explanation: str
    findings_explanation: str
    domain_explanation: str
    excerpts: List[RelevanceExcerpt] = Field(default_factory=list)
    positive_signals: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    decision: str  # INCLUDE, REVIEW, EXCLUDE
    is_metadata_only: bool = False


class PaperRelevanceEvaluator:
    """Evaluates paper relevance using LLM semantic assessment with deterministic scoring and facet decomposition."""

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        direct_weight: float = DEFAULT_DIRECT_WEIGHT,
        methodology_weight: float = DEFAULT_METHODOLOGY_WEIGHT,
        findings_weight: float = DEFAULT_FINDINGS_WEIGHT,
        domain_weight: float = DEFAULT_DOMAIN_WEIGHT,
        include_threshold: float = DEFAULT_INCLUDE_THRESHOLD,
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    ):
        self.llm = llm_provider
        self.direct_weight = direct_weight
        self.methodology_weight = methodology_weight
        self.findings_weight = findings_weight
        self.domain_weight = domain_weight
        self.include_threshold = include_threshold
        self.review_threshold = review_threshold

    def calculate_deterministic_score(
        self,
        direct: float,
        methodology: float,
        findings: float,
        domain: float,
        evidence_role: str = "DIRECT_EVIDENCE",
    ) -> tuple[float, str]:
        """Calculates deterministic weighted score and maps to decision threshold, factoring in evidence role."""
        direct = max(0.0, min(100.0, float(direct)))
        methodology = max(0.0, min(100.0, float(methodology)))
        findings = max(0.0, min(100.0, float(findings)))
        domain = max(0.0, min(100.0, float(domain)))

        score = (
            self.direct_weight * direct
            + self.methodology_weight * methodology
            + self.findings_weight * findings
            + self.domain_weight * domain
        )
        score = round(score, 2)

        # Evidence role policy:
        # BACKGROUND_CONTEXT papers provide valuable context (e.g. vector db cost, differential privacy)
        # but are not direct comparative QA evidence; they are retained under REVIEW.
        # IRRELEVANT papers are EXCLUDE.
        if evidence_role == "IRRELEVANT":
            decision = "EXCLUDE"
            score = min(score, 35.0)
        elif evidence_role == "BACKGROUND_CONTEXT":
            decision = "REVIEW"
            score = min(score, 65.0)
        elif score >= self.include_threshold:
            decision = "INCLUDE"
        elif score >= self.review_threshold:
            decision = "REVIEW"
        else:
            decision = "EXCLUDE"

        return score, decision

    async def evaluate_source(
        self,
        source: Dict[str, Any],
        research_question: str,
        passages: Optional[List[Dict[str, Any]]] = None,
    ) -> StructuredRelevanceResult:
        """Evaluates a single retrieved source against the research inquiry."""
        source_id = source.get("id", "unknown_source")
        title = source.get("title", "Untitled")
        abstract = source.get("abstract") or ""
        access_status = source.get("access_status", "metadata_only")
        inspected_full = source.get("inspected_full_text", 0) == 1

        is_metadata_only = bool(not passages and not abstract) or (access_status == "metadata_only" and not abstract)

        # Build context from actual source data ONLY
        context_parts = [f"Title: {title}"]
        if source.get("authors"):
            context_parts.append(f"Authors: {source['authors']}")
        if source.get("publication_year"):
            context_parts.append(f"Year: {source['publication_year']}")
        if abstract:
            context_parts.append(f"Abstract: {abstract}")

        if passages:
            context_parts.append("Available Passages:")
            for idx, p in enumerate(passages[:5]):
                page_info = f" (Page {p.get('page_number')})" if p.get("page_number") else ""
                context_parts.append(f"- Passage {idx+1}{page_info}: {p.get('passage_text', '')}")

        source_context = "\n".join(context_parts)

        # System prompt enforcing factual extraction, facet decomposition, and evidence role classification
        system_prompt = (
            "You are a rigorous SCHOLARLY RELEVANCE EVALUATOR in an autonomous academic research system.\n"
            "Your objective is to evaluate whether a retrieved paper directly addresses the research question:\n"
            f"'{research_question}'\n\n"
            "RESEARCH FACETS TO EVALUATE:\n"
            "1. factual_accuracy: Does the paper assess factual precision, grounding, or hallucination reduction in question answering?\n"
            "2. knowledge_freshness: Does the paper address updating models or retrieving up-to-date domain knowledge?\n"
            "3. computational_cost: Does the paper evaluate training compute, GPU expenditures, or inference latency/cost?\n"
            "4. limitations: Does the paper discuss inherent limitations, failure modes, or trade-offs?\n\n"
            "EVIDENCE ROLE DISTINCTION:\n"
            "- DIRECT_EVIDENCE: Paper directly investigates or empirically compares RAG and Fine-Tuning (or specifically investigates either for domain QA).\n"
            "- BACKGROUND_CONTEXT: Paper investigates tangential topics (e.g. fake-news detection, vector database cost attribution, differential privacy, openCTI) that mention RAG or cost as an implementation detail but do NOT provide direct comparative evidence for domain QA.\n"
            "- IRRELEVANT: Paper is off-topic.\n\n"
            "CRITICAL SAFEGUARD: A paper about fake news detection, vector index cost attribution, or differential privacy must NOT be marked DIRECT_EVIDENCE merely because it mentions RAG or cost. Classify it as BACKGROUND_CONTEXT with direct_relevance scored conservatively (20-45).\n\n"
            "Output strictly valid JSON with the schema:\n"
            "{\n"
            '  "evidence_role": "DIRECT_EVIDENCE | BACKGROUND_CONTEXT | IRRELEVANT",\n'
            '  "facet_coverage": {\n'
            '    "factual_accuracy": true,\n'
            '    "knowledge_freshness": false,\n'
            '    "computational_cost": true,\n'
            '    "limitations": true\n'
            '  },\n'
            '  "direct_relevance": 85,\n'
            '  "methodology_relevance": 70,\n'
            '  "findings_relevance": 80,\n'
            '  "domain_relevance": 90,\n'
            '  "direct_explanation": "Directly evaluates RAG vs fine-tuning trade-offs in domain QA",\n'
            '  "methodology_explanation": "Compares parameter-efficient fine-tuning with dense vector retrieval",\n'
            '  "findings_explanation": "Reports concrete hallucination rate reductions and latency metrics",\n'
            '  "domain_explanation": "Natural language processing and machine learning domain",\n'
            '  "positive_signals": ["Direct comparative study of RAG vs Fine-Tuning", "Empirical latency metrics"],\n'
            '  "missing_information": ["Full-text evaluation omitted; abstract only"],\n'
            '  "excerpts": [\n'
            '    {"text": "We measure knowledge freshness, GPU training expenditures...", "provenance": "abstract"}\n'
            "  ]\n"
            "}"
        )

        user_prompt = (
            f"Research Question: {research_question}\n\n"
            f"Source Evidence ({'Metadata Only' if is_metadata_only else 'Abstract/Full-Text informed'}):\n"
            f"{source_context}\n\n"
            "Evaluate paper relevance according to the guidelines."
        )

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        llm_data: Dict[str, Any] = {}
        try:
            resp = await self.llm.generate(messages, temperature=0.1, response_format_json=True)
            parsed = extract_structured_json(resp.content)
            if isinstance(parsed, dict) and "direct_relevance" in parsed:
                llm_data = parsed
        except Exception as first_err:
            logger.warning("Relevance evaluation JSON parse failed (%s). Attempting repair...", first_err)
            repair_messages = messages + [
                LLMMessage(role="assistant", content=resp.content if "resp" in locals() else ""),
                LLMMessage(role="user", content="Formatting error. Output ONLY valid JSON matching the schema with numerical scores and explanation strings."),
            ]
            try:
                repair_resp = await self.llm.generate(repair_messages, temperature=0.1, response_format_json=True)
                parsed = extract_structured_json(repair_resp.content)
                if isinstance(parsed, dict) and "direct_relevance" in parsed:
                    llm_data = parsed
            except Exception as repair_err:
                logger.warning("Relevance repair failed (%s). Using conservative fallback.", repair_err)

        if not llm_data:
            # Fallback evaluation based on exact matching and metadata inspection
            llm_data = self._heuristic_fallback(source, research_question, is_metadata_only)

        # Extract role and facet coverage
        role = str(llm_data.get("evidence_role", "DIRECT_EVIDENCE")).upper()
        if role not in ("DIRECT_EVIDENCE", "BACKGROUND_CONTEXT", "IRRELEVANT"):
            role = "BACKGROUND_CONTEXT" if float(llm_data.get("direct_relevance", 50.0)) < 60 else "DIRECT_EVIDENCE"

        raw_facets = llm_data.get("facet_coverage") or {}
        facet_coverage = {
            "factual_accuracy": bool(raw_facets.get("factual_accuracy", False)),
            "knowledge_freshness": bool(raw_facets.get("knowledge_freshness", False)),
            "computational_cost": bool(raw_facets.get("computational_cost", False)),
            "limitations": bool(raw_facets.get("limitations", False)),
        }

        # Deterministic score calculation in Python
        direct = float(llm_data.get("direct_relevance", 50.0))
        methodology = float(llm_data.get("methodology_relevance", 50.0))
        findings = float(llm_data.get("findings_relevance", 50.0))
        domain = float(llm_data.get("domain_relevance", 50.0))

        weighted_score, decision = self.calculate_deterministic_score(
            direct=direct,
            methodology=methodology,
            findings=findings,
            domain=domain,
            evidence_role=role,
        )

        # Parse excerpts
        parsed_excerpts: List[RelevanceExcerpt] = []
        for exc in llm_data.get("excerpts", []):
            if isinstance(exc, dict) and exc.get("text"):
                parsed_excerpts.append(
                    RelevanceExcerpt(
                        text=str(exc["text"]).strip(),
                        provenance=str(exc.get("provenance", "abstract")),
                    )
                )

        if not parsed_excerpts:
            # Provide at least title provenance
            parsed_excerpts.append(RelevanceExcerpt(text=title, provenance="title"))

        pos_signals = [str(s) for s in llm_data.get("positive_signals", []) if s]
        covered_facets_str = ", ".join([k.replace("_", " ").title() for k, v in facet_coverage.items() if v])
        if covered_facets_str:
            pos_signals.insert(0, f"Facets addressed: {covered_facets_str}")
        pos_signals.insert(0, f"Evidence Role: {role.replace('_', ' ').title()}")

        missing_info = [str(m) for m in llm_data.get("missing_information", []) if m]
        if is_metadata_only and "Metadata-only source; abstract and full text unavailable." not in missing_info:
            missing_info.append("Metadata-only source; abstract and full text unavailable.")

        return StructuredRelevanceResult(
            source_id=source_id,
            research_question=research_question,
            relevance_score=weighted_score,
            direct_relevance=direct,
            methodology_relevance=methodology,
            findings_relevance=findings,
            domain_relevance=domain,
            evidence_role=role,
            facet_coverage=facet_coverage,
            direct_explanation=llm_data.get("direct_explanation", "Direct topical relevance assessed."),
            methodology_explanation=llm_data.get("methodology_explanation", "Methodological alignment assessed."),
            findings_explanation=llm_data.get("findings_explanation", "Empirical findings alignment assessed."),
            domain_explanation=llm_data.get("domain_explanation", "Domain scope assessed."),
            excerpts=parsed_excerpts,
            positive_signals=pos_signals,
            missing_information=missing_info,
            decision=decision,
            is_metadata_only=is_metadata_only,
        )

    def _heuristic_fallback(
        self,
        source: Dict[str, Any],
        research_question: str,
        is_metadata_only: bool,
    ) -> Dict[str, Any]:
        """Conservative deterministic fallback when LLM parsing is unavailable."""
        title = (source.get("title") or "").lower()
        abstract = (source.get("abstract") or "").lower()
        full_text = f"{title} {abstract}"

        # Decompose research facets
        facet_coverage = {
            "factual_accuracy": any(t in full_text for t in ["accuracy", "hallucination", "precision", "factual", "faithfulness", "fact-checking"]),
            "knowledge_freshness": any(t in full_text for t in ["freshness", "update", "temporal", "dynamic", "real-time", "recent"]),
            "computational_cost": any(t in full_text for t in ["cost", "compute", "gpu", "latency", "memory", "throughput", "overhead"]),
            "limitations": any(t in full_text for t in ["limitation", "failure", "trade-off", "bottleneck", "challenge", "risk"]),
        }

        # Check for core paradigms
        has_rag = any(t in full_text for t in ["rag", "retrieval-augmented", "retrieval augmented"])
        has_ft = any(t in full_text for t in ["fine-tuning", "finetuning", "fine tuning", "fine-tuned", "peft", "lora"])

        # Detect tangential / application papers that mention RAG or cost but do not compare RAG vs Fine-Tuning
        is_tangential = any(
            phrase in full_text for phrase in [
                "fake news", "misinformation", "differential privacy", "per-tenant cost",
                "turbovec", "opencti", "cyber threat", "multi-tenant"
            ]
        )

        if is_tangential and not (has_rag and has_ft):
            role = "BACKGROUND_CONTEXT"
            direct = 35.0
            method = 50.0
            findings = 45.0
            domain = 75.0
            direct_exp = "Investigates specialized application or infrastructure; provides background context rather than direct RAG vs Fine-Tuning QA comparison."
        elif has_rag and has_ft:
            role = "DIRECT_EVIDENCE"
            direct = 85.0
            method = 80.0
            findings = 80.0
            domain = 90.0
            direct_exp = "Directly investigates or compares both retrieval-augmented generation and fine-tuning."
        elif has_rag or has_ft:
            role = "BACKGROUND_CONTEXT"
            direct = 55.0
            method = 60.0
            findings = 55.0
            domain = 80.0
            direct_exp = "Examines one target technique (RAG or Fine-Tuning) in detail; provides relevant background context."
        else:
            role = "IRRELEVANT"
            direct = 20.0
            method = 25.0
            findings = 20.0
            domain = 40.0
            direct_exp = "Lacks direct or contextual alignment with RAG and Fine-Tuning research inquiries."

        if is_metadata_only:
            method = min(method, 45.0)
            findings = min(findings, 40.0)

        return {
            "evidence_role": role,
            "facet_coverage": facet_coverage,
            "direct_relevance": direct,
            "methodology_relevance": method,
            "findings_relevance": findings,
            "domain_relevance": domain,
            "direct_explanation": direct_exp,
            "methodology_explanation": "Methodology assessed from abstract and publication context.",
            "findings_explanation": "Empirical findings relevance estimated from available text.",
            "domain_explanation": "Domain concordance evaluated against natural language processing literature.",
            "positive_signals": [f"Role: {role}"],
            "missing_information": ["Full-text deep inspection was not performed."] if not is_metadata_only else ["Metadata-only source."],
            "excerpts": [{"text": (source.get("abstract") or source.get("title") or "")[:200], "provenance": "abstract" if source.get("abstract") else "title"}],
        }
