"""
Agent 4: Fact-Checking Agent.
Independently verifies factual claims against stored evidence passages using deterministic
database provenance verification and semantic LLM entailment.

Allowed Verification Statuses:
- SUPPORTED: Passage logically and directly corroborates all material aspects of the claim.
- PARTIALLY_SUPPORTED: Passage supports core premises, but claim overstates or lacks complete corroboration.
- CONTRADICTED: Passage directly refutes or provides contradicting evidence against the claim.
- INSUFFICIENT_EVIDENCE: Passage is missing, uninformative, or lacks defensible corroboration.
- INVALID_CITATION: Cited source ID or passage ID does not exist in SQLite, or cited passage belongs to a different source.

NOTE ON CONFIDENCE METRIC:
The confidence score (0.0 to 1.0) is a heuristic model assessment of textual alignment, NOT a
mathematically calibrated probability distribution.
"""

from __future__ import annotations

import difflib
import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.database.repositories import (
    ClaimRepository,
    EvidenceRepository,
    SourceRepository,
    VerificationRepository,
)
from app.llm.base import BaseLLMProvider, LLMMessage
from app.llm.json_repair import extract_structured_json

logger = logging.getLogger(__name__)

ALLOWED_VERDICTS = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "INSUFFICIENT_EVIDENCE",
    "INVALID_CITATION",
}


def _map_legacy_verdict(status: str) -> str:
    """Maps modern verification status to legacy test verdict strings for backward compatibility."""
    if status == "INSUFFICIENT_EVIDENCE":
        return "NOT_CHECKABLE"
    if status == "INVALID_CITATION":
        return "UNSUPPORTED"
    if status == "CONTRADICTED":
        return "CONFLICTING"
    return status


class ClaimAuditRecord(BaseModel):
    claim_id: str
    claim_text: str
    source_ids: List[str] = Field(default_factory=list)
    passage_ids: List[str] = Field(default_factory=list)
    exact_supporting_excerpts: List[str] = Field(default_factory=list)
    verification_status: str  # One of ALLOWED_VERDICTS
    verdict: str  # Alias for backward compatibility
    explanation: str
    rationale: str  # Alias for backward compatibility
    contradicting_evidence: Optional[str] = None
    contradiction_found: bool = False
    verification_method: str = "deterministic_provenance_check + semantic_llm_entailment"
    confidence: float = 0.0  # Heuristic score, not calibrated probability
    support_score: float = 0.0  # Alias for backward compatibility
    is_direct_quote: bool = False


class VerificationAuditResult(BaseModel):
    run_id: str
    total_claims_audited: int
    supported_count: int
    partially_supported_count: int
    contradicted_count: int
    insufficient_evidence_count: int
    invalid_citation_count: int
    needs_retry: bool
    retry_subquestions: List[str]
    audits: List[ClaimAuditRecord]

    # Backward compatibility properties
    @property
    def unsupported_count(self) -> int:
        return self.contradicted_count + self.insufficient_evidence_count

    @property
    def conflicting_count(self) -> int:
        return self.contradicted_count

    @property
    def not_checkable_count(self) -> int:
        return self.invalid_citation_count + self.insufficient_evidence_count


class FactCheckingAgent:
    """Audits claims against stored evidence with strict deterministic provenance and semantic verification."""

    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm = llm_provider

    async def verify_claims(
        self, run_id: str, retry_budget_remaining: int = 2
    ) -> VerificationAuditResult:
        """Audits every claim registered for the run, persisting verdicts to SQLite."""
        claims = ClaimRepository.list_by_run(run_id)
        if not claims:
            logger.info("No claims found to verify for run %s", run_id)
            return VerificationAuditResult(
                run_id=run_id,
                total_claims_audited=0,
                supported_count=0,
                partially_supported_count=0,
                contradicted_count=0,
                insufficient_evidence_count=0,
                invalid_citation_count=0,
                needs_retry=False,
                retry_subquestions=[],
                audits=[],
            )

        sources = SourceRepository.list_by_run(run_id)
        source_map = {s["id"]: s for s in sources}
        all_passages = EvidenceRepository.list_by_run(run_id)
        passage_map = {p["id"]: p for p in all_passages}

        audits: List[ClaimAuditRecord] = []
        retry_subquestions: List[str] = []

        for claim in claims:
            claim_id = claim["id"]
            claim_text = claim["claim_text"]
            subq = claim.get("subquestion_id")
            ev_list = claim.get("evidence", [])

            audit_item = await self._audit_single_claim(
                claim_id=claim_id,
                claim_text=claim_text,
                ev_list=ev_list,
                source_map=source_map,
                passage_map=passage_map,
            )

            # Check if retry is warranted for this subquestion
            if audit_item.verification_status in ("CONTRADICTED", "INSUFFICIENT_EVIDENCE", "INVALID_CITATION"):
                if retry_budget_remaining > 0 and subq and subq not in retry_subquestions:
                    retry_subquestions.append(subq)

            # Persist to SQLite
            VerificationRepository.record(
                claim_id=claim_id,
                run_id=run_id,
                verdict=audit_item.verification_status,
                rationale=audit_item.explanation,
                support_score=audit_item.confidence,
                contradiction_found=audit_item.contradiction_found,
                contradicting_evidence=audit_item.contradicting_evidence,
                supporting_excerpts=audit_item.exact_supporting_excerpts,
                verification_method=audit_item.verification_method,
                confidence=audit_item.confidence,
                is_direct_quote=audit_item.is_direct_quote,
            )

            audits.append(audit_item)

        supp_c = sum(1 for a in audits if a.verification_status == "SUPPORTED")
        part_c = sum(1 for a in audits if a.verification_status == "PARTIALLY_SUPPORTED")
        contra_c = sum(1 for a in audits if a.verification_status == "CONTRADICTED")
        insuff_c = sum(1 for a in audits if a.verification_status == "INSUFFICIENT_EVIDENCE")
        inv_c = sum(1 for a in audits if a.verification_status == "INVALID_CITATION")

        needs_retry = (
            retry_budget_remaining > 0
            and len(retry_subquestions) > 0
            and (supp_c / max(1, len(audits)) < 0.6)
        )

        return VerificationAuditResult(
            run_id=run_id,
            total_claims_audited=len(audits),
            supported_count=supp_c,
            partially_supported_count=part_c,
            contradicted_count=contra_c,
            insufficient_evidence_count=insuff_c,
            invalid_citation_count=inv_c,
            needs_retry=needs_retry,
            retry_subquestions=retry_subquestions,
            audits=audits,
        )

    async def _audit_single_claim(
        self,
        claim_id: str,
        claim_text: str,
        ev_list: List[Dict[str, Any]],
        source_map: Dict[str, Dict[str, Any]],
        passage_map: Dict[str, Dict[str, Any]],
    ) -> ClaimAuditRecord:
        """Executes separate deterministic provenance check and semantic entailment evaluation."""
        source_ids = list(set(ev.get("source_id") for ev in ev_list if ev.get("source_id")))
        passage_ids = [ev.get("id") for ev in ev_list if ev.get("id")]

        # Direct quote detection heuristic
        is_quote = self._detect_direct_quote(claim_text, ev_list)

        # -------------------------------------------------------------
        # 1. Deterministic Checks
        # -------------------------------------------------------------
        if not ev_list or not passage_ids:
            return ClaimAuditRecord(
                claim_id=claim_id,
                claim_text=claim_text,
                source_ids=source_ids,
                passage_ids=passage_ids,
                exact_supporting_excerpts=[],
                verification_status="INSUFFICIENT_EVIDENCE",
                verdict="NOT_CHECKABLE",
                explanation="Claim has no linked evidence citations or passages in the database. It does not cite any registered evidence.",
                rationale="Claim has no linked evidence citations or passages in the database. It does not cite any registered evidence.",
                contradicting_evidence=None,
                contradiction_found=False,
                verification_method="deterministic_registry_check",
                confidence=0.0,
                support_score=0.0,
                is_direct_quote=is_quote,
            )

        # Check for missing source IDs
        for sid in source_ids:
            if sid not in source_map:
                return ClaimAuditRecord(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    source_ids=source_ids,
                    passage_ids=passage_ids,
                    exact_supporting_excerpts=[],
                    verification_status="INVALID_CITATION",
                    verdict="INVALID_CITATION",
                    explanation=f"Referenced source ID '{sid}' does not exist in SQLite sources repository.",
                    rationale=f"Referenced source ID '{sid}' does not exist in SQLite sources repository.",
                    contradicting_evidence=None,
                    contradiction_found=False,
                    verification_method="deterministic_foreign_key_check",
                    confidence=0.0,
                    support_score=0.0,
                    is_direct_quote=is_quote,
                )

        # Check for missing passage IDs
        for pid in passage_ids:
            if pid not in passage_map:
                return ClaimAuditRecord(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    source_ids=source_ids,
                    passage_ids=passage_ids,
                    exact_supporting_excerpts=[],
                    verification_status="INVALID_CITATION",
                    verdict="INVALID_CITATION",
                    explanation=f"Referenced passage ID '{pid}' does not exist in SQLite evidence repository.",
                    rationale=f"Referenced passage ID '{pid}' does not exist in SQLite evidence repository.",
                    contradicting_evidence=None,
                    contradiction_found=False,
                    verification_method="deterministic_foreign_key_check",
                    confidence=0.0,
                    support_score=0.0,
                    is_direct_quote=is_quote,
                )

        # Check source-to-passage provenance (passage must belong to the cited source)
        for ev in ev_list:
            pid = ev.get("id")
            claimed_sid = ev.get("source_id")
            actual_passage = passage_map.get(pid)
            if actual_passage and actual_passage.get("source_id") != claimed_sid:
                return ClaimAuditRecord(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    source_ids=source_ids,
                    passage_ids=passage_ids,
                    exact_supporting_excerpts=[],
                    verification_status="INVALID_CITATION",
                    verdict="INVALID_CITATION",
                    explanation=(
                        f"Provenance mismatch: passage '{pid}' belongs to source "
                        f"'{actual_passage.get('source_id')}', not cited source '{claimed_sid}'."
                    ),
                    rationale=(
                        f"Provenance mismatch: passage '{pid}' belongs to source "
                        f"'{actual_passage.get('source_id')}', not cited source '{claimed_sid}'."
                    ),
                    contradicting_evidence=None,
                    contradiction_found=False,
                    verification_method="deterministic_provenance_check",
                    confidence=0.0,
                    support_score=0.0,
                    is_direct_quote=is_quote,
                )

        # -------------------------------------------------------------
        # 2. Semantic LLM Entailment Check
        # -------------------------------------------------------------
        return await self._evaluate_semantic_entailment(
            claim_id=claim_id,
            claim_text=claim_text,
            source_ids=source_ids,
            passage_ids=passage_ids,
            evidence_list=ev_list,
            is_direct_quote=is_quote,
        )

    async def _evaluate_semantic_entailment(
        self,
        claim_id: str,
        claim_text: str,
        source_ids: List[str],
        passage_ids: List[str],
        evidence_list: List[Dict[str, Any]],
        is_direct_quote: bool,
    ) -> ClaimAuditRecord:
        """Calls LLM to assess logical entailment, extracts supporting excerpts, and flags contradictions."""
        passages_formatted = []
        for idx, ev in enumerate(evidence_list):
            passages_formatted.append(
                f"[Evidence Passage {idx+1} | Source: {ev.get('source_title', 'Unknown')} | EvID: {ev.get('id')}]:\n"
                f"{ev.get('passage_text', '')}"
            )
        joined_text = "\n\n".join(passages_formatted)

        system_prompt = (
            "You are an academic FACT-CHECKING AGENT verifying scientific claims against evidence passages.\n"
            "Assess whether the supplied passage logically and empirically supports the claim.\n"
            "Rules:\n"
            "1. Matching keywords alone is NOT proof of support. The passage must logically entail the claim.\n"
            "2. If the passage contradicts or refutes the claim, mark CONTRADICTED and quote the contradicting text.\n"
            "3. If the passage only supports part of the claim or the claim overstates findings, mark PARTIALLY_SUPPORTED.\n"
            "4. If the passage is off-topic or insufficient to confirm the claim, mark INSUFFICIENT_EVIDENCE.\n"
            "5. If all material aspects of the claim are directly confirmed by the text, mark SUPPORTED.\n"
            "6. Identify the exact supporting excerpts from the text. Never fabricate quotations.\n"
            "7. Output strictly valid JSON matching this schema:\n"
            "{\n"
            '  "verification_status": "SUPPORTED | PARTIALLY_SUPPORTED | CONTRADICTED | INSUFFICIENT_EVIDENCE",\n'
            '  "explanation": "Clear academic justification citing specific passage details",\n'
            '  "exact_supporting_excerpts": ["Exact phrase from passage that supports the claim"],\n'
            '  "contradicting_evidence": "Exact phrase from passage that contradicts the claim, or null",\n'
            '  "confidence": 0.90\n'
            "}"
        )

        user_prompt = f"Claim to Audit: {claim_text}\n\nEvidence Passages:\n{joined_text}\n"

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        llm_data: Dict[str, Any] = {}
        def _extract_llm_data(raw_obj):
            if isinstance(raw_obj, dict):
                if "verification_status" in raw_obj:
                    return raw_obj
                if "verifications" in raw_obj and isinstance(raw_obj["verifications"], list) and raw_obj["verifications"]:
                    item = raw_obj["verifications"][0]
                    return {
                        "verification_status": item.get("verdict", "SUPPORTED"),
                        "explanation": item.get("rationale", "Evidence corroborates claim."),
                        "exact_supporting_excerpts": item.get("exact_supporting_excerpts", [item.get("rationale", "")]),
                        "contradicting_evidence": item.get("contradicting_evidence"),
                        "confidence": item.get("support_score", 0.90),
                    }
                if "verdict" in raw_obj:
                    return {
                        "verification_status": raw_obj.get("verdict"),
                        "explanation": raw_obj.get("rationale", raw_obj.get("explanation", "")),
                        "exact_supporting_excerpts": raw_obj.get("exact_supporting_excerpts", []),
                        "contradicting_evidence": raw_obj.get("contradicting_evidence"),
                        "confidence": raw_obj.get("support_score", raw_obj.get("confidence", 0.85)),
                    }
            return None

        try:
            resp = await self.llm.generate(messages, temperature=0.1, response_format_json=True)
            parsed = extract_structured_json(resp.content)
            extracted = _extract_llm_data(parsed)
            if extracted:
                llm_data = extracted
        except Exception as first_err:
            logger.warning("Fact-checker LLM JSON parse error (%s). Attempting repair...", first_err)
            repair_messages = messages + [
                LLMMessage(role="assistant", content=resp.content if "resp" in locals() else ""),
                LLMMessage(role="user", content="Invalid JSON. Output ONLY valid JSON with verification_status, explanation, exact_supporting_excerpts, contradicting_evidence, and confidence."),
            ]
            try:
                repair_resp = await self.llm.generate(repair_messages, temperature=0.1, response_format_json=True)
                parsed = extract_structured_json(repair_resp.content)
                extracted = _extract_llm_data(parsed)
                if extracted:
                    llm_data = extracted
            except Exception as repair_err:
                logger.warning("Fact-checker repair failed (%s). Using conservative fallback.", repair_err)

        if not llm_data:
            # Conservative deterministic fallback
            return self._heuristic_fallback(
                claim_id=claim_id,
                claim_text=claim_text,
                source_ids=source_ids,
                passage_ids=passage_ids,
                evidence_list=evidence_list,
                is_direct_quote=is_direct_quote,
            )

        status = str(llm_data.get("verification_status", "INSUFFICIENT_EVIDENCE")).upper()
        if status not in ALLOWED_VERDICTS or status == "INVALID_CITATION":
            status = "PARTIALLY_SUPPORTED"

        explanation = str(llm_data.get("explanation", "Evaluated against stored evidence passages."))
        contra_ev = llm_data.get("contradicting_evidence")
        if contra_ev:
            contra_ev = str(contra_ev).strip()
            if status != "CONTRADICTED" and len(contra_ev) > 10:
                status = "CONTRADICTED"

        contra_found = bool(status == "CONTRADICTED" or contra_ev)
        conf = float(llm_data.get("confidence", 0.80 if status == "SUPPORTED" else 0.50))
        conf = max(0.0, min(1.0, conf))

        excerpts = [str(x).strip() for x in llm_data.get("exact_supporting_excerpts", []) if x]

        # Requirement 7: If the model cannot provide a defensible explanation, use INSUFFICIENT_EVIDENCE
        if len(explanation.strip()) < 15 and status == "SUPPORTED":
            status = "INSUFFICIENT_EVIDENCE"
            explanation = "Insufficient explanatory justification provided by auditor model; conservative downgrade."

        return ClaimAuditRecord(
            claim_id=claim_id,
            claim_text=claim_text,
            source_ids=source_ids,
            passage_ids=passage_ids,
            exact_supporting_excerpts=excerpts,
            verification_status=status,
            verdict=_map_legacy_verdict(status),
            explanation=explanation,
            rationale=explanation,
            contradicting_evidence=contra_ev,
            contradiction_found=contra_found,
            verification_method="semantic_llm_entailment",
            confidence=conf,
            support_score=conf,
            is_direct_quote=is_direct_quote,
        )

    def _heuristic_fallback(
        self,
        claim_id: str,
        claim_text: str,
        source_ids: List[str],
        passage_ids: List[str],
        evidence_list: List[Dict[str, Any]],
        is_direct_quote: bool,
    ) -> ClaimAuditRecord:
        """Conservative deterministic fallback when LLM is unavailable or fails."""
        # Check for explicit contradictions in text
        claim_lower = claim_text.lower()
        combined_text = " ".join(ev.get("passage_text", "") for ev in evidence_list).lower()

        # Check for negation words indicating contradiction
        negations = ["does not", "cannot", "failed to", "no evidence", "refuted", "contrary to", "disproven"]
        has_negation = any(neg in combined_text for neg in negations)

        # Requirement 6: Do not treat matching keywords alone as proof of support!
        # If model is unavailable, classify conservatively as PARTIALLY_SUPPORTED or INSUFFICIENT_EVIDENCE
        claim_words = set(w for w in re.findall(r"\w+", claim_lower) if len(w) > 3)
        passage_words = set(w for w in re.findall(r"\w+", combined_text) if len(w) > 3)

        overlap = len(claim_words.intersection(passage_words)) / max(1, len(claim_words))

        if is_direct_quote and overlap > 0.8:
            status = "SUPPORTED"
            explanation = "Direct verbatim quotation corroborates claim text in evidence passage."
            confidence = 0.90
        elif overlap > 0.6 and not has_negation:
            status = "PARTIALLY_SUPPORTED"
            explanation = "Substantial conceptual alignment observed; deeper semantic entailment requires manual review."
            confidence = 0.65
        elif has_negation and overlap > 0.4:
            status = "CONTRADICTED"
            explanation = "Passage contains explicit qualifying or negating terms that challenge the factual claim."
            confidence = 0.70
        else:
            status = "INSUFFICIENT_EVIDENCE"
            explanation = "Evidence text is insufficient or conceptually distant from the asserted claim."
            confidence = 0.40

        # Extract matching excerpt
        excerpts = []
        for ev in evidence_list:
            text = ev.get("passage_text", "")
            if any(w in text.lower() for w in list(claim_words)[:3]):
                excerpts.append(text[:150] + "...")
                break

        return ClaimAuditRecord(
            claim_id=claim_id,
            claim_text=claim_text,
            source_ids=source_ids,
            passage_ids=passage_ids,
            exact_supporting_excerpts=excerpts,
            verification_status=status,
            verdict=_map_legacy_verdict(status),
            explanation=explanation,
            rationale=explanation,
            contradicting_evidence="Potential negation observed in source passage." if status == "CONTRADICTED" else None,
            contradiction_found=(status == "CONTRADICTED"),
            verification_method="deterministic_heuristic_fallback",
            confidence=confidence,
            support_score=confidence,
            is_direct_quote=is_direct_quote,
        )

    def _detect_direct_quote(self, claim_text: str, evidence_list: List[Dict[str, Any]]) -> bool:
        """Determines if a claim is a direct quote versus a paraphrase."""
        clean_claim = claim_text.strip()
        # Explicit quotes in text
        if (clean_claim.startswith('"') and clean_claim.endswith('"')) or (clean_claim.startswith("'") and clean_claim.endswith("'")):
            return True

        # Check for 6+ consecutive matching words in any passage
        claim_tokens = re.findall(r"\w+", clean_claim.lower())
        if len(claim_tokens) >= 6:
            claim_phrase = " ".join(claim_tokens[:6])
            for ev in evidence_list:
                p_tokens = " ".join(re.findall(r"\w+", ev.get("passage_text", "").lower()))
                if claim_phrase in p_tokens:
                    return True
        return False
