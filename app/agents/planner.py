"""
Agent 1: Planner Agent.
Validates the research question, decomposes it into research subquestions,
generates targeted academic search queries, and specifies evidence expectations.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.llm.base import BaseLLMProvider, LLMMessage
from app.llm.json_repair import extract_structured_json

logger = logging.getLogger(__name__)


class SubquestionSpec(BaseModel):
    id: str
    title: str
    description: str
    search_queries: List[str]
    expected_evidence: str


class ResearchPlan(BaseModel):
    plan_id: str
    research_question: str
    objectives: List[str]
    subquestions: List[SubquestionSpec]
    target_sections: List[str]


class PlannerAgent:
    """Decomposes a research question into an actionable academic research plan."""

    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm = llm_provider

    def validate_question(self, question: str) -> Optional[str]:
        """Validates research question; returns error string if invalid, else None."""
        if not question or not question.strip():
            return "Research question cannot be empty or solely whitespace."
        q = question.strip()
        if len(q) < 10:
            return "Research question is too short to formulate an academic investigation (minimum 10 characters)."
        if len(q) > 1000:
            return "Research question exceeds maximum length limit (1000 characters)."
        return None

    async def create_plan(self, question: str) -> ResearchPlan:
        """Generates a structured research plan using LLM or structured rules."""
        validation_error = self.validate_question(question)
        if validation_error:
            raise ValueError(validation_error)

        system_prompt = (
            "You are the PLANNER AGENT in an autonomous academic research system.\n"
            "Your objective is to decompose a complex scholarly research question into a rigorous research plan.\n"
            "Requirements:\n"
            "1. Define at least 3 distinct research subquestions.\n"
            "2. Generate 2 targeted academic search queries per subquestion suitable for OpenAlex/arXiv. Use concise natural language keywords without underscores or punctuation (e.g. 'retrieval augmented generation domain question answering').\n"
            "3. Specify expected empirical or theoretical evidence.\n"
            "4. Define report outline sections.\n"
            "Output strictly valid JSON conforming to the schema:\n"
            "{\n"
            '  "plan_id": "string",\n'
            '  "research_question": "string",\n'
            '  "objectives": ["string"],\n'
            '  "subquestions": [\n'
            '    {\n'
            '      "id": "sq-1",\n'
            '      "title": "string",\n'
            '      "description": "string",\n'
            '      "search_queries": ["string", "string"],\n'
            '      "expected_evidence": "string"\n'
            "    }\n"
            "  ],\n"
            '  "target_sections": ["string"]\n'
            "}"
        )

        user_prompt = f'Research Question: "{question.strip()}"'

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        response = await self.llm.generate(messages, temperature=0.2, response_format_json=True)
        try:
            data = extract_structured_json(response.content)
            if not isinstance(data, dict):
                raise ValueError(f"Expected JSON object, got {type(data).__name__}")
            data["research_question"] = question.strip()
            return ResearchPlan(**data)
        except Exception as first_err:
            logger.warning("Initial planner JSON parsing failed (%s). Attempting 1-shot repair...", first_err)
            repair_messages = messages + [
                LLMMessage(role="assistant", content=response.content),
                LLMMessage(role="user", content="The previous output contained syntax errors or markdown. Output ONLY the raw JSON object matching the requested schema without any markdown, backticks, or introductory text."),
            ]
            try:
                repair_resp = await self.llm.generate(repair_messages, temperature=0.1, response_format_json=True)
                data = extract_structured_json(repair_resp.content)
                if not isinstance(data, dict):
                    raise ValueError(f"Expected JSON object after repair, got {type(data).__name__}")
                data["research_question"] = question.strip()
                return ResearchPlan(**data)
            except Exception as repair_err:
                logger.error("Planner Agent failed to produce valid JSON: %s", repair_err)
                raise ValueError(f"Planner Agent failed to produce valid research plan JSON: {repair_err}") from repair_err

    def _build_fallback_plan(self, question: str) -> ResearchPlan:
        """Deterministic fallback when JSON parsing fails."""
        clean_q = question.strip()
        return ResearchPlan(
            plan_id="plan-fallback-01",
            research_question=clean_q,
            objectives=[
                f"Examine theoretical and architectural principles of: {clean_q}",
                "Evaluate comparative empirical performance, latency, and cost trade-offs",
                "Identify limitations, failure modes, and unresolved research gaps",
            ],
            subquestions=[
                SubquestionSpec(
                    id="sq-1",
                    title="Architectural Foundations",
                    description=f"Core technical mechanisms for {clean_q}",
                    search_queries=[f"{clean_q} architecture", f"{clean_q} survey"],
                    expected_evidence="Architectural descriptions and algorithmic trade-offs.",
                ),
                SubquestionSpec(
                    id="sq-2",
                    title="Empirical Benchmarks & Metrics",
                    description=f"Comparative performance metrics for {clean_q}",
                    search_queries=[f"{clean_q} benchmark accuracy", f"{clean_q} latency cost"],
                    expected_evidence="Quantitative accuracy and resource consumption metrics.",
                ),
                SubquestionSpec(
                    id="sq-3",
                    title="Limitations & Open Problems",
                    description=f"Vulnerabilities and future directions for {clean_q}",
                    search_queries=[f"{clean_q} limitations challenges", f"{clean_q} failure modes"],
                    expected_evidence="Documented failure cases, vulnerability audits, and research gaps.",
                ),
            ],
            target_sections=[
                "Executive Summary",
                "Methodology & Objectives",
                "Foundational Principles",
                "Comparative Evaluation",
                "Critical Limitations",
                "Future Directions",
                "Conclusion & References",
            ],
        )
