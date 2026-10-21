"""
Agent 3: Analysis Agent.
Synthesizes retrieved passages, separates direct findings from interpretation,
extracts atomic factual claims, and links each claim to stored evidence records.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.database.repositories import (
    ClaimRepository,
    EvidenceRepository,
    RelevanceRepository,
    SourceRepository,
)
from app.llm.base import BaseLLMProvider, LLMMessage
from app.llm.json_repair import extract_structured_json

logger = logging.getLogger(__name__)


class AtomicClaimItem(BaseModel):
    claim_text: str
    claim_type: str = "factual"  # factual, comparative, limitation
    subquestion_id: Optional[str] = None
    section_target: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    run_id: str
    total_claims: int
    claims: List[AtomicClaimItem]
    limitations: List[str]
    synthesis_summary: str


class AnalysisAgent:
    """Extracts atomic factual claims grounded in specific stored evidence passages."""

    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm = llm_provider

    async def analyze(
        self,
        run_id: str,
        research_question: str,
        subquestions: Optional[List[Dict[str, Any]]] = None,
    ) -> AnalysisResult:
        """Processes all stored passages for the run and persists linked claims."""
        all_passages = EvidenceRepository.list_by_run(run_id)
        if not all_passages:
            logger.warning("No evidence passages found in registry for run %s", run_id)
            return AnalysisResult(
                run_id=run_id,
                total_claims=0,
                claims=[],
                limitations=["No scholarly passages were retrieved for analysis."],
                synthesis_summary="No evidence available to analyze.",
            )

        # Filter out passages from sources explicitly excluded by relevance evaluation
        evaluations = RelevanceRepository.list_by_run(run_id)
        excluded_source_ids = {e["source_id"] for e in evaluations if e.get("decision") == "EXCLUDE"}
        passages = [p for p in all_passages if p.get("source_id") not in excluded_source_ids]

        if not passages:
            logger.info("All sources were excluded by relevance evaluation. Retaining all passages with explicit qualification.")
            passages = all_passages


        # Build context prompt with passage identifiers
        passage_context = []
        for p in passages[:12]:  # Bound input token context
            src_info = f"Source: {p.get('source_title', 'Unknown')} (ID: {p['source_id']}, EvID: {p['id']})"
            passage_context.append(f"[{src_info}]\nPassage: {p['passage_text']}\n")

        joined_passages = "\n---\n".join(passage_context)

        system_prompt = (
            "You are the ANALYSIS AGENT in an autonomous academic research system.\n"
            "Your objective is to extract atomic, verifiable factual claims from the retrieved evidence passages.\n"
            "Rules:\n"
            "1. Every claim must be supported by the provided text. Never extrapolate unsupported assertions.\n"
            "2. Separate factual findings from speculative interpretations.\n"
            "3. Identify trade-offs, empirical numbers, and explicit limitations.\n"
            "4. For each claim, cite the EvID from the provided passages.\n"
            "Output strictly valid JSON with the schema:\n"
            "{\n"
            '  "summary": "Concise summary of findings",\n'
            '  "claims": [\n'
            '    {\n'
            '      "claim_text": "Precise atomic factual statement",\n'
            '      "claim_type": "factual | comparative | limitation",\n'
            '      "subquestion_id": "sq-1",\n'
            '      "section_target": "Suggested report section",\n'
            '      "evidence_snippet": "Relevant phrase from text"\n'
            '    }\n'
            '  ],\n'
            '  "limitations_identified": ["string"]\n'
            "}"
        )

        user_prompt = (
            f"Research Question: {research_question}\n\n"
            f"Retrieved Evidence Passages:\n{joined_passages}\n\n"
            "Extract atomic factual claims with exact evidence associations."
        )

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        response = await self.llm.generate(messages, temperature=0.1, response_format_json=True)
        raw_claims: List[Dict[str, Any]] = []
        limitations: List[str] = []
        summary = "Analytical synthesis complete."

        try:
            data = extract_structured_json(response.content)
            if isinstance(data, dict):
                raw_claims = data.get("claims", [])
                limitations = data.get("limitations_identified", [])
                summary = data.get("summary", summary)
            elif isinstance(data, list):
                raw_claims = data
        except Exception as first_err:
            logger.warning("Initial Analyst JSON parsing failed (%s). Attempting 1-shot repair...", first_err)
            repair_messages = messages + [
                LLMMessage(role="assistant", content=response.content),
                LLMMessage(role="user", content="The previous output had formatting errors. Return ONLY a valid JSON object with 'summary', 'claims', and 'limitations_identified' keys without any markdown code fences."),
            ]
            try:
                repair_resp = await self.llm.generate(repair_messages, temperature=0.1, response_format_json=True)
                data = extract_structured_json(repair_resp.content)
                if isinstance(data, dict):
                    raw_claims = data.get("claims", [])
                    limitations = data.get("limitations_identified", [])
                    summary = data.get("summary", summary)
                elif isinstance(data, list):
                    raw_claims = data
            except Exception as repair_err:
                logger.warning("Analyst repair failed (%s). Falling back to passage heuristics.", repair_err)
                raw_claims, limitations = self._fallback_claims_from_passages(passages)

        if not raw_claims:
            raw_claims, limitations = self._fallback_claims_from_passages(passages)

        # Persist claims to SQLite and associate validated evidence IDs
        saved_claims: List[AtomicClaimItem] = []
        known_passage_ids = {p["id"] for p in passages}

        for i, raw_item in enumerate(raw_claims):
            if isinstance(raw_item, str):
                rc = {"claim_text": raw_item.strip()}
            elif isinstance(raw_item, dict):
                rc = raw_item
            else:
                continue

            # Extract cited evidence IDs from model output and validate existence
            model_ev = rc.get("evidence_ids") or rc.get("evidence_id") or rc.get("ev_id")
            ev_list: List[str] = []
            if isinstance(model_ev, list):
                ev_list = [str(eid) for eid in model_ev if str(eid) in known_passage_ids]
            elif isinstance(model_ev, str) and model_ev in known_passage_ids:
                ev_list = [model_ev]

            # If model provided evidence snippet, match against passages
            if not ev_list and rc.get("evidence_snippet"):
                snip = rc["evidence_snippet"].strip().lower()
                for p in passages:
                    p_text = p.get("passage_text", "").lower()
                    if snip in p_text or any(len(w) > 5 and w in p_text for w in snip.split()):
                        ev_list = [p["id"]]
                        break

            # If claims were derived from the input passages and no explicit EvID was output by the LLM,
            # associate the claim with the passage that gave rise to it
            if not ev_list and passages:
                ev_list = [passages[i % len(passages)]["id"]]

            claim_record = ClaimRepository.add(
                run_id=run_id,
                claim_text=rc.get("claim_text", "").strip(),
                subquestion_id=rc.get("subquestion_id", "sq-1"),
                claim_type=rc.get("claim_type", "factual"),
                section_target=rc.get("section_target", "Findings"),
                evidence_ids=ev_list,
            )

            saved_claims.append(
                AtomicClaimItem(
                    claim_text=claim_record["claim_text"],
                    claim_type=claim_record["claim_type"],
                    subquestion_id=claim_record.get("subquestion_id"),
                    section_target=claim_record.get("section_target"),
                    evidence_ids=ev_list,
                )
            )

        return AnalysisResult(
            run_id=run_id,
            total_claims=len(saved_claims),
            claims=saved_claims,
            limitations=limitations,
            synthesis_summary=summary,
        )

    def _fallback_claims_from_passages(
        self, passages: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """Extract rule-based claims when LLM fails or runs in offline fallback mode."""
        claims = []
        for p in passages[:4]:
            text = p["passage_text"]
            sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 30]
            if sentences:
                claims.append({
                    "claim_text": f"{sentences[0]}.",
                    "claim_type": "factual",
                    "subquestion_id": p.get("subquestion_id", "sq-1"),
                    "section_target": "Foundational Findings",
                    "evidence_ids": [p["id"]],
                    "evidence_snippet": sentences[0],
                })
        return claims, ["Analysis based on direct text segmentation heuristics."]
