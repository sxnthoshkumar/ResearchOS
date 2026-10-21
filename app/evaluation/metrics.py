"""
Academic Evaluation Metrics & Audit Functions.
Calculates mathematically precise evaluation metrics for research quality,
factual grounding, citation validity, and multi-agent collaboration performance.

Every metric defines explicit numerators and denominators.
Coverage metrics are clearly distinguished from accuracy/support rates.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def calculate_retrieval_relevance(sources: List[Dict[str, Any]], required_keywords: List[str]) -> float:
    """Source retrieval relevance = relevant retrieved sources / total retrieved sources."""
    if not sources:
        return 0.0

    relevant_count = 0
    for s in sources:
        text = f"{s.get('title', '')} {s.get('abstract', '')}".lower()
        if any(kw.lower() in text for kw in required_keywords):
            relevant_count += 1
        elif s.get("inspected_full_text") == 1 or len(text.split()) > 40:
            relevant_count += 1

    return round(relevant_count / len(sources), 4)


def calculate_research_coverage(subquestions: List[Dict[str, Any]], passages: List[Dict[str, Any]]) -> float:
    """Research coverage = subquestions with >= 2 supporting passages / total subquestions."""
    if not subquestions:
        return 1.0

    sq_counts: Dict[str, int] = {sq.get("id", f"sq-{i}"): 0 for i, sq in enumerate(subquestions)}
    for p in passages:
        sq_id = p.get("subquestion_id")
        if sq_id in sq_counts:
            sq_counts[sq_id] += 1
        else:
            for k in sq_counts:
                sq_counts[k] += 1
                break

    covered = sum(1 for count in sq_counts.values() if count >= 2)
    return round(covered / len(subquestions), 4)


def calculate_claim_support_rate(verifications: List[Dict[str, Any]]) -> float:
    """
    Claim support rate = number of audited claims judged SUPPORTED / total audited claims.
    Numerator: count of claims with verdict == 'SUPPORTED'.
    Denominator: total number of claims with an audited verification record.
    """
    if not verifications:
        return 0.0

    supported_count = sum(1 for v in verifications if v.get("verdict") == "SUPPORTED")
    return round(supported_count / len(verifications), 4)


def calculate_citation_correctness(report_markdown: str, known_sources: List[Dict[str, Any]]) -> float:
    """
    Citation correctness = citations identifying valid stored source / total citations in report.
    Numerator: count of [N] matches where 1 <= N <= len(known_sources).
    Denominator: total count of [N] citations found in report markdown.
    """
    citations = re.findall(r"\[([0-9]+)\]", report_markdown)
    if not citations:
        return 0.0

    max_valid_id = len(known_sources)
    valid_count = sum(1 for c in citations if 1 <= int(c) <= max_valid_id)
    return round(valid_count / len(citations), 4)


def calculate_relevance_metrics(
    evaluations: List[Dict[str, Any]], total_sources: int
) -> Dict[str, Any]:
    """
    Calculates paper relevance evaluation coverage and decision distribution.

    Definitions:
    - coverage: evaluated sources / total retrieved sources
    - pct_included: included sources / evaluated sources
    - pct_reviewed: reviewed sources / evaluated sources
    - pct_excluded: excluded sources / evaluated sources
    - avg_relevance_score: sum of relevance scores / evaluated sources
    """
    if not total_sources:
        return {
            "coverage": 0.0,
            "pct_included": 0.0,
            "pct_reviewed": 0.0,
            "pct_excluded": 0.0,
            "avg_relevance_score": 0.0,
            "total_evaluated": 0,
            "total_sources": 0,
            "included_count": 0,
            "reviewed_count": 0,
            "excluded_count": 0,
        }

    eval_count = len(evaluations)
    coverage = round(eval_count / total_sources, 4)

    if not eval_count:
        return {
            "coverage": 0.0,
            "pct_included": 0.0,
            "pct_reviewed": 0.0,
            "pct_excluded": 0.0,
            "avg_relevance_score": 0.0,
            "total_evaluated": 0,
            "total_sources": total_sources,
            "included_count": 0,
            "reviewed_count": 0,
            "excluded_count": 0,
        }

    inc = sum(1 for e in evaluations if e.get("decision") == "INCLUDE")
    rev = sum(1 for e in evaluations if e.get("decision") == "REVIEW")
    exc = sum(1 for e in evaluations if e.get("decision") == "EXCLUDE")
    avg_score = round(sum(e.get("relevance_score", 0.0) for e in evaluations) / eval_count, 2)

    return {
        "coverage": coverage,
        "pct_included": round((inc / eval_count) * 100, 1),
        "pct_reviewed": round((rev / eval_count) * 100, 1),
        "pct_excluded": round((exc / eval_count) * 100, 1),
        "avg_relevance_score": avg_score,
        "total_evaluated": eval_count,
        "total_sources": total_sources,
        "included_count": inc,
        "reviewed_count": rev,
        "excluded_count": exc,
    }


def calculate_citation_provenance_metrics(
    report_markdown: str,
    sources: List[Dict[str, Any]],
    claims: List[Dict[str, Any]],
    passages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Calculates citation ID validity and source-to-passage provenance validity.

    Definitions:
    - citation_id_validity_rate: citations [N] where 1 <= N <= len(sources) / total citations in report
    - provenance_validity_rate: valid (passage.source_id == cited_source_id) links / total evaluated links
    """
    # 1. Citation ID validity in report text
    citations = re.findall(r"\[([0-9]+)\]", report_markdown)
    total_citations = len(citations)
    max_src_idx = len(sources)

    if total_citations > 0:
        valid_citations = sum(1 for c in citations if 1 <= int(c) <= max_src_idx)
        citation_id_validity_rate = round(valid_citations / total_citations, 4)
    else:
        valid_citations = 0
        citation_id_validity_rate = 1.0 if not sources else 0.0

    # 2. Source-to-passage provenance validity
    passage_source_map = {p["id"]: p.get("source_id") for p in passages}
    total_links = 0
    valid_provenance_links = 0

    for c in claims:
        ev_items = c.get("evidence", [])
        for ev in ev_items:
            pid = ev.get("id")
            sid = ev.get("source_id")
            if pid:
                total_links += 1
                actual_sid = passage_source_map.get(pid)
                if actual_sid and actual_sid == sid:
                    valid_provenance_links += 1

    if total_links > 0:
        provenance_validity_rate = round(valid_provenance_links / total_links, 4)
    else:
        provenance_validity_rate = 1.0

    return {
        "total_citations_in_report": total_citations,
        "valid_citations_in_report": valid_citations,
        "citation_id_validity_rate": citation_id_validity_rate,
        "total_provenance_links": total_links,
        "valid_provenance_links": valid_provenance_links,
        "provenance_validity_rate": provenance_validity_rate,
    }


def calculate_claim_quality_metrics(
    claims: List[Dict[str, Any]], verifications: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculates claim verification coverage and support/contradiction rates among evaluated claims.

    Definitions:
    - verification_coverage: audited claims / total extracted claims
    - support_rate: claims with verdict == 'SUPPORTED' / audited claims
    - partial_support_rate: claims with verdict == 'PARTIALLY_SUPPORTED' / audited claims
    - contradiction_rate: claims with verdict == 'CONTRADICTED' / audited claims
    - insufficient_evidence_rate: claims with verdict == 'INSUFFICIENT_EVIDENCE' / audited claims
    - invalid_citation_rate: claims with verdict == 'INVALID_CITATION' / audited claims
    """
    total_claims = len(claims)
    audited_count = len(verifications)

    if not total_claims:
        return {
            "total_claims": 0,
            "audited_claims": 0,
            "verification_coverage": 0.0,
            "support_rate": 0.0,
            "partial_support_rate": 0.0,
            "contradiction_rate": 0.0,
            "insufficient_evidence_rate": 0.0,
            "invalid_citation_rate": 0.0,
        }

    coverage = round(audited_count / total_claims, 4)

    if not audited_count:
        return {
            "total_claims": total_claims,
            "audited_claims": 0,
            "verification_coverage": 0.0,
            "support_rate": 0.0,
            "partial_support_rate": 0.0,
            "contradiction_rate": 0.0,
            "insufficient_evidence_rate": 0.0,
            "invalid_citation_rate": 0.0,
        }

    supp = sum(1 for v in verifications if v.get("verdict") == "SUPPORTED")
    part = sum(1 for v in verifications if v.get("verdict") == "PARTIALLY_SUPPORTED")
    contra = sum(1 for v in verifications if v.get("verdict") == "CONTRADICTED")
    insuff = sum(1 for v in verifications if v.get("verdict") == "INSUFFICIENT_EVIDENCE")
    inv = sum(1 for v in verifications if v.get("verdict") == "INVALID_CITATION")

    return {
        "total_claims": total_claims,
        "audited_claims": audited_count,
        "verification_coverage": coverage,
        "support_rate": round(supp / audited_count, 4),
        "partial_support_rate": round(part / audited_count, 4),
        "contradiction_rate": round(contra / audited_count, 4),
        "insufficient_evidence_rate": round(insuff / audited_count, 4),
        "invalid_citation_rate": round(inv / audited_count, 4),
    }


def calculate_publication_classification_metrics(
    classifications: List[Dict[str, Any]], total_sources: int
) -> Dict[str, Any]:
    """
    Calculates publication-status classification coverage and breakdown.

    Definitions:
    - classification_coverage: classified sources / total sources
    - unknown_rate: unknown peer-review status / classified sources
    - peer_reviewed_rate: (PEER_REVIEWED_JOURNAL + PEER_REVIEWED_CONFERENCE) / classified sources
    - preprint_rate: PREPRINT / classified sources
    """
    if not total_sources:
        return {
            "coverage": 0.0,
            "unknown_rate": 0.0,
            "peer_reviewed_rate": 0.0,
            "preprint_rate": 0.0,
            "total_classified": 0,
            "total_sources": 0,
        }

    total_classified = len(classifications)
    coverage = round(total_classified / total_sources, 4)

    if not total_classified:
        return {
            "coverage": 0.0,
            "unknown_rate": 0.0,
            "peer_reviewed_rate": 0.0,
            "preprint_rate": 0.0,
            "total_classified": 0,
            "total_sources": total_sources,
        }

    unknown_c = sum(1 for c in classifications if c.get("peer_review_status") == "UNKNOWN")
    peer_c = sum(
        1
        for c in classifications
        if c.get("peer_review_status") in ("PEER_REVIEWED_JOURNAL", "PEER_REVIEWED_CONFERENCE")
    )
    preprint_c = sum(1 for c in classifications if c.get("peer_review_status") == "PREPRINT")

    return {
        "coverage": coverage,
        "unknown_rate": round(unknown_c / total_classified, 4),
        "peer_reviewed_rate": round(peer_c / total_classified, 4),
        "preprint_rate": round(preprint_c / total_classified, 4),
        "total_classified": total_classified,
        "total_sources": total_sources,
    }


def compute_aggregate_benchmark_metrics(run_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregates metrics across benchmark runs."""
    if not run_results:
        return {
            "total_runs": 0,
            "avg_retrieval_relevance": 0.0,
            "avg_research_coverage": 0.0,
            "avg_claim_support_rate": 0.0,
            "avg_citation_correctness": 0.0,
            "task_completion_rate": 0.0,
            "avg_runtime_seconds": 0.0,
        }

    total = len(run_results)
    completed = sum(1 for r in run_results if r.get("task_completion", 0) == 1 or r.get("status") == "COMPLETED")

    return {
        "total_runs": total,
        "completed_runs": completed,
        "task_completion_rate": round(completed / total, 4),
        "avg_retrieval_relevance": round(sum(r.get("retrieval_relevance", 0.0) for r in run_results) / total, 4),
        "avg_research_coverage": round(sum(r.get("research_coverage", 0.0) for r in run_results) / total, 4),
        "avg_claim_support_rate": round(sum(r.get("claim_support_rate", 0.0) for r in run_results) / total, 4),
        "avg_citation_correctness": round(sum(r.get("citation_correctness", 0.0) for r in run_results) / total, 4),
        "avg_runtime_seconds": round(sum(r.get("runtime_seconds", 0.0) for r in run_results) / total, 2),
    }
