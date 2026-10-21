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
    """Evaluates paper relevance using LLM semantic assessment with deterministic scoring."""

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
    ) -> tuple[float, str]:
        """Calculates deterministic weighted score and maps to decision threshold."""
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

        if score >= self.include_threshold:
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

        # System prompt enforcing factual extraction and component scoring
        system_prompt = (
            "You are a rigorous SCHOLARLY RELEVANCE EVALUATOR in an autonomous academic research system.\n"
            "Your objective is to evaluate whether a retrieved paper directly addresses the research question.\n"
            "Rules:\n"
            "1. Evaluate ONLY the provided title, abstract, and passages. Never invent findings, methods, or quotations.\n"
            "2. Score each component from 0 to 100 based strictly on provided text:\n"
            "   - direct_relevance: Does the paper directly investigate the core question?\n"
            "   - methodology_relevance: Are the research methods, datasets, or techniques relevant?\n"
            "   - findings_relevance: Does the paper present findings directly informing the question?\n"
            "   - domain_relevance: Does the paper belong to the relevant academic domain or discipline?\n"
            "3. If only a title or brief metadata is available, do not pretend findings or methodology are confirmed; "
            "score findings/methodology conservatively (e.g. 30-50) and note missing information.\n"
            "4. Provide exact excerpts from the provided text showing provenance (title, abstract, or passage).\n"
            "Output strictly valid JSON with the schema:\n"
            "{\n"
            '  "direct_relevance": 85,\n'
            '  "methodology_relevance": 70,\n'
            '  "findings_relevance": 80,\n'
            '  "domain_relevance": 90,\n'
            '  "direct_explanation": "Directly evaluates retrieval-augmented generation architectures",\n'
            '  "methodology_explanation": "Compares parameter-efficient fine-tuning with dense vector retrieval",\n'
            '  "findings_explanation": "Reports concrete hallucination rate reductions and latency metrics",\n'
            '  "domain_explanation": "Natural language processing and machine learning domain",\n'
            '  "positive_signals": ["Explicit comparison between RAG and fine-tuning", "Empirical latency metrics"],\n'
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

        q_tokens = [w for w in re.findall(r"[a-zA-Z0-9]+", research_question.lower()) if len(w) > 2]
        stopwords = {"compare", "focusing", "for", "and", "the", "with", "from", "that", "this", "between", "across", "what", "how"}
        meaningful_q = [w for w in q_tokens if w not in stopwords]

        if not meaningful_q:
            overlap_ratio = 0.5
        else:
            matched_words = [w for w in meaningful_q if w in full_text]
            overlap_ratio = len(matched_words) / len(meaningful_q)

        has_core = any(term in full_text for term in ["rag", "retrieval", "fine-tuning", "fine tuning", "finetuning", "fine-tuned", "llm", "language model", "question answering"])
        has_facet = any(term in full_text for term in ["accuracy", "freshness", "cost", "computational", "limitation", "domain", "evaluation", "benchmark"])

        if is_metadata_only:
            # Conservative: cannot confirm findings or methodology, mark REVIEW or EXCLUDE
            base_direct = min(80.0, overlap_ratio * 120)
            if has_core:
                base_direct = max(base_direct, 60.0)
            direct = round(base_direct, 1)
            return {
                "direct_relevance": direct,
                "methodology_relevance": 45.0,
                "findings_relevance": 40.0,
                "domain_relevance": 70.0 if has_core else 50.0,
                "direct_explanation": "Keyword alignment observed in metadata, but detailed contents unavailable.",
                "methodology_explanation": "Methodology cannot be verified from metadata alone.",
                "findings_explanation": "Empirical findings cannot be verified without abstract or full-text.",
                "domain_explanation": "Subject area inferred from publication title.",
                "positive_signals": ["Title keywords correspond with research inquiry."],
                "missing_information": ["Abstract and full-text unavailable; metadata-only evaluation."],
                "excerpts": [{"text": source.get("title", ""), "provenance": "title"}],
            }

        # Abstract / Passages available
        base_direct = min(95.0, max(20.0, overlap_ratio * 130))
        base_method = min(90.0, max(25.0, overlap_ratio * 110))
        base_findings = min(90.0, max(20.0, overlap_ratio * 110))
        base_domain = min(95.0, max(30.0, overlap_ratio * 120))

        if has_core and has_facet:
            base_direct = max(base_direct, 80.0)
            base_method = max(base_method, 75.0)
            base_findings = max(base_findings, 75.0)
            base_domain = max(base_domain, 85.0)
        elif has_core:
            base_direct = max(base_direct, 65.0)
            base_domain = max(base_domain, 75.0)

        direct = round(base_direct, 1)
        method = round(base_method, 1)
        findings = round(base_findings, 1)
        domain = round(base_domain, 1)

        return {
            "direct_relevance": direct,
            "methodology_relevance": method,
            "findings_relevance": findings,
            "domain_relevance": domain,
            "direct_explanation": f"Keyword overlap analysis yields {round(overlap_ratio * 100)}% conceptual term match.",
            "methodology_explanation": "Methodology inferred from abstract terminology.",
            "findings_explanation": "Empirical findings relevance estimated from abstract summary.",
            "domain_explanation": "Domain concordance determined from lexical matching.",
            "positive_signals": ["Term overlap with research question in title/abstract."],
            "missing_information": ["Full-text deep inspection was not performed."],
            "excerpts": [{"text": (source.get("abstract") or source.get("title") or "")[:200], "provenance": "abstract" if source.get("abstract") else "title"}],
        }
