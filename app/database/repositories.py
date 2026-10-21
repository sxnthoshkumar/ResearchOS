"""
Database Repositories for Research Projects, Runs, Tasks, Sources, Evidence, Claims, Verifications, and Reports.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.database.db import db_manager

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectRepository:
    @staticmethod
    def create(title: str, description: Optional[str] = None) -> Dict[str, Any]:
        project_id = str(uuid.uuid4())
        now = utc_now_iso()
        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO research_projects (id, title, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (project_id, title.strip(), description.strip() if description else "", now, now),
            )
        return {
            "id": project_id,
            "title": title.strip(),
            "description": description or "",
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def get(project_id: str) -> Optional[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            row = conn.execute("SELECT * FROM research_projects WHERE id = ?;", (project_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute("SELECT * FROM research_projects ORDER BY created_at DESC;").fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def delete(project_id: str) -> bool:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("DELETE FROM research_projects WHERE id = ?;", (project_id,))
            return cursor.rowcount > 0


class RunRepository:
    @staticmethod
    def create(
        project_id: str,
        question: str,
        provider_mode: str = "demo",
        model_name: Optional[str] = None,
        search_providers: str = "openalex,arxiv",
        max_sources: int = 10,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        now = utc_now_iso()
        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO research_runs (
                    id, project_id, question, status, provider_mode, model_name,
                    search_providers, max_sources, retry_count, max_retries,
                    start_time, created_at, updated_at
                ) VALUES (?, ?, ?, 'CREATED', ?, ?, ?, ?, 0, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    project_id,
                    question.strip(),
                    provider_mode,
                    model_name or "",
                    search_providers,
                    max_sources,
                    max_retries,
                    now,
                    now,
                    now,
                ),
            )
        return RunRepository.get(run_id)  # type: ignore

    @staticmethod
    def get(run_id: str) -> Optional[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            row = conn.execute("SELECT * FROM research_runs WHERE id = ?;", (run_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_status(
        run_id: str,
        status: str,
        error_message: Optional[str] = None,
        completed: bool = False,
    ) -> None:
        now = utc_now_iso()
        with db_manager.get_connection() as conn:
            if completed:
                run = RunRepository.get(run_id)
                duration = 0.0
                if run and run.get("start_time"):
                    try:
                        start_dt = datetime.fromisoformat(run["start_time"])
                        duration = (datetime.now(timezone.utc) - start_dt).total_seconds()
                    except Exception:
                        pass
                conn.execute(
                    """
                    UPDATE research_runs
                    SET status = ?, error_message = ?, completed_time = ?, duration_seconds = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (status, error_message, now, duration, now, run_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE research_runs
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (status, error_message, now, run_id),
                )

    @staticmethod
    def increment_retry(run_id: str) -> int:
        now = utc_now_iso()
        with db_manager.get_connection() as conn:
            conn.execute(
                """
                UPDATE research_runs
                SET retry_count = retry_count + 1, updated_at = ?
                WHERE id = ?;
                """,
                (now, run_id),
            )
            row = conn.execute("SELECT retry_count FROM research_runs WHERE id = ?;", (run_id,)).fetchone()
            return int(row["retry_count"]) if row else 0

    @staticmethod
    def list_by_project(project_id: str) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM research_runs WHERE project_id = ? ORDER BY created_at DESC;",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def list_all(limit: int = 50) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM research_runs ORDER BY created_at DESC LIMIT ?;",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]


class TaskRepository:
    @staticmethod
    def create(
        run_id: str,
        agent_name: str,
        task_name: str,
        input_data: Optional[Dict[str, Any]] = None,
        retry_attempt: int = 0,
    ) -> Dict[str, Any]:
        task_id = str(uuid.uuid4())
        now = utc_now_iso()
        input_json = json.dumps(input_data) if input_data is not None else None
        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_tasks (
                    id, run_id, agent_name, task_name, status,
                    input_data, start_time, retry_attempt, created_at
                ) VALUES (?, ?, ?, ?, 'RUNNING', ?, ?, ?, ?);
                """,
                (task_id, run_id, agent_name, task_name, input_json, now, retry_attempt, now),
            )
        return {
            "id": task_id,
            "run_id": run_id,
            "agent_name": agent_name,
            "task_name": task_name,
            "status": "RUNNING",
            "start_time": now,
        }

    @staticmethod
    def finish(
        task_id: str,
        status: str,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        now = utc_now_iso()
        output_json = json.dumps(output_data) if output_data is not None else None
        with db_manager.get_connection() as conn:
            task = conn.execute("SELECT start_time FROM agent_tasks WHERE id = ?;", (task_id,)).fetchone()
            duration = 0.0
            if task and task["start_time"]:
                try:
                    start_dt = datetime.fromisoformat(task["start_time"])
                    duration = (datetime.now(timezone.utc) - start_dt).total_seconds()
                except Exception:
                    pass
            conn.execute(
                """
                UPDATE agent_tasks
                SET status = ?, output_data = ?, error_message = ?, end_time = ?, duration_seconds = ?
                WHERE id = ?;
                """,
                (status, output_json, error_message, now, duration, task_id),
            )

    @staticmethod
    def list_by_run(run_id: str) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_tasks WHERE run_id = ? ORDER BY created_at ASC;",
                (run_id,),
            ).fetchall()
            tasks = []
            for r in rows:
                item = dict(r)
                if item.get("input_data"):
                    try:
                        item["input_data"] = json.loads(item["input_data"])
                    except Exception:
                        pass
                if item.get("output_data"):
                    try:
                        item["output_data"] = json.loads(item["output_data"])
                    except Exception:
                        pass
                tasks.append(item)
            return tasks


class SourceRepository:
    @staticmethod
    def add(
        run_id: str,
        title: str,
        authors: Optional[str | List[str]] = None,
        publication_year: Optional[int] = None,
        abstract: Optional[str] = None,
        doi: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        canonical_url: Optional[str] = None,
        provider: str = "openalex",
        access_status: str = "abstract_only",
        doc_type: str = "article",
        inspected_full_text: int = 0,
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        source_id = str(uuid.uuid4())
        now = utc_now_iso()
        authors_str = (
            ", ".join(authors) if isinstance(authors, list) else (authors or "Unknown")
        )
        raw_meta_str = json.dumps(raw_metadata) if raw_metadata else None

        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sources (
                    id, run_id, title, authors, publication_year, abstract,
                    doi, arxiv_id, canonical_url, provider, access_status,
                    doc_type, inspected_full_text, raw_metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    source_id,
                    run_id,
                    title.strip(),
                    authors_str,
                    publication_year,
                    abstract,
                    doi.strip() if doi else None,
                    arxiv_id.strip() if arxiv_id else None,
                    canonical_url,
                    provider,
                    access_status,
                    doc_type,
                    inspected_full_text,
                    raw_meta_str,
                    now,
                ),
            )
        return SourceRepository.get(source_id)  # type: ignore

    @staticmethod
    def get(source_id: str) -> Optional[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id = ?;", (source_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_by_run(run_id: str) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sources WHERE run_id = ? ORDER BY created_at ASC;",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def find_duplicate(
        run_id: str,
        doi: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            if doi:
                row = conn.execute(
                    "SELECT * FROM sources WHERE run_id = ? AND LOWER(doi) = LOWER(?);",
                    (run_id, doi.strip()),
                ).fetchone()
                if row:
                    return dict(row)
            if arxiv_id:
                row = conn.execute(
                    "SELECT * FROM sources WHERE run_id = ? AND LOWER(arxiv_id) = LOWER(?);",
                    (run_id, arxiv_id.strip()),
                ).fetchone()
                if row:
                    return dict(row)
            if title:
                # Conservative title check
                normalized_title = "".join(ch for ch in title.lower() if ch.isalnum())
                all_sources = conn.execute(
                    "SELECT * FROM sources WHERE run_id = ?;", (run_id,)
                ).fetchall()
                for s in all_sources:
                    existing_norm = "".join(ch for ch in s["title"].lower() if ch.isalnum())
                    if existing_norm and existing_norm == normalized_title:
                        return dict(s)
            return None


class EvidenceRepository:
    @staticmethod
    def add_passage(
        source_id: str,
        run_id: str,
        passage_text: str,
        page_number: Optional[int] = None,
        extraction_method: str = "abstract",
        subquestion_id: Optional[str] = None,
        relevance_score: float = 1.0,
    ) -> Dict[str, Any]:
        passage_id = str(uuid.uuid4())
        now = utc_now_iso()
        clean_text = passage_text.strip()
        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO evidence_passages (
                    id, source_id, run_id, passage_text, page_number,
                    extraction_method, subquestion_id, relevance_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    passage_id,
                    source_id,
                    run_id,
                    clean_text,
                    page_number,
                    extraction_method,
                    subquestion_id,
                    relevance_score,
                    now,
                ),
            )
            # Sync to FTS5 if supported
            if db_manager.is_fts_available():
                try:
                    conn.execute(
                        "INSERT INTO evidence_fts (evidence_id, passage_text) VALUES (?, ?);",
                        (passage_id, clean_text),
                    )
                except Exception as e:
                    logger.debug("FTS insert note: %s", e)

        return {
            "id": passage_id,
            "source_id": source_id,
            "run_id": run_id,
            "passage_text": clean_text,
            "page_number": page_number,
            "extraction_method": extraction_method,
            "subquestion_id": subquestion_id,
            "relevance_score": relevance_score,
            "created_at": now,
        }

    @staticmethod
    def list_by_run(run_id: str) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT ep.*, s.title as source_title, s.doi, s.arxiv_id, s.provider
                FROM evidence_passages ep
                JOIN sources s ON ep.source_id = s.id
                WHERE ep.run_id = ?
                ORDER BY ep.created_at ASC;
                """,
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def list_by_source(source_id: str) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence_passages WHERE source_id = ? ORDER BY page_number ASC, created_at ASC;",
                (source_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def search(run_id: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            if db_manager.is_fts_available():
                try:
                    # Clean query for FTS MATCH
                    sanitized_words = [w for w in query.split() if w.isalnum()]
                    if sanitized_words:
                        fts_query = " OR ".join(sanitized_words)
                        rows = conn.execute(
                            """
                            SELECT ep.*, s.title as source_title, s.doi, s.arxiv_id
                            FROM evidence_fts fts
                            JOIN evidence_passages ep ON fts.evidence_id = ep.id
                            JOIN sources s ON ep.source_id = s.id
                            WHERE ep.run_id = ? AND evidence_fts MATCH ?
                            LIMIT ?;
                            """,
                            (run_id, fts_query, limit),
                        ).fetchall()
                        if rows:
                            return [dict(r) for r in rows]
                except Exception as e:
                    logger.debug("FTS query fallback triggered: %s", e)

            # Fallback to LIKE search
            term = f"%{query.strip()}%"
            rows = conn.execute(
                """
                SELECT ep.*, s.title as source_title, s.doi, s.arxiv_id
                FROM evidence_passages ep
                JOIN sources s ON ep.source_id = s.id
                WHERE ep.run_id = ? AND ep.passage_text LIKE ?
                LIMIT ?;
                """,
                (run_id, term, limit),
            ).fetchall()
            return [dict(r) for r in rows]


class ClaimRepository:
    @staticmethod
    def add(
        run_id: str,
        claim_text: str,
        subquestion_id: Optional[str] = None,
        claim_type: str = "factual",
        section_target: Optional[str] = None,
        evidence_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        claim_id = str(uuid.uuid4())
        now = utc_now_iso()
        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO claims (id, run_id, subquestion_id, claim_text, claim_type, section_target, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (claim_id, run_id, subquestion_id, claim_text.strip(), claim_type, section_target, now),
            )
            if evidence_ids:
                for eid in evidence_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO claim_evidence (claim_id, evidence_id) VALUES (?, ?);",
                        (claim_id, eid),
                    )

        return ClaimRepository.get(claim_id)  # type: ignore

    @staticmethod
    def get(claim_id: str) -> Optional[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            row = conn.execute("SELECT * FROM claims WHERE id = ?;", (claim_id,)).fetchone()
            if not row:
                return None
            claim = dict(row)
            # Fetch linked evidence
            ev_rows = conn.execute(
                """
                SELECT ep.*, s.title as source_title, s.doi, s.arxiv_id, s.provider
                FROM claim_evidence ce
                JOIN evidence_passages ep ON ce.evidence_id = ep.id
                JOIN sources s ON ep.source_id = s.id
                WHERE ce.claim_id = ?;
                """,
                (claim_id,),
            ).fetchall()
            claim["evidence"] = [dict(e) for e in ev_rows]
            return claim

    @staticmethod
    def list_by_run(run_id: str) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM claims WHERE run_id = ? ORDER BY created_at ASC;", (run_id,)
            ).fetchall()
            result = []
            for r in rows:
                claim = dict(r)
                ev_rows = conn.execute(
                    """
                    SELECT ep.id, ep.source_id, ep.passage_text, ep.page_number, s.title as source_title, s.doi, s.arxiv_id
                    FROM claim_evidence ce
                    JOIN evidence_passages ep ON ce.evidence_id = ep.id
                    JOIN sources s ON ep.source_id = s.id
                    WHERE ce.claim_id = ?;
                    """,
                    (claim["id"],),
                ).fetchall()
                claim["evidence"] = [dict(e) for e in ev_rows]
                result.append(claim)
            return result


class VerificationRepository:
    @staticmethod
    def record(
        claim_id: str,
        run_id: str,
        verdict: str,
        rationale: str,
        support_score: float = 0.0,
        contradiction_found: bool = False,
        contradicting_evidence: Optional[str] = None,
        supporting_excerpts: Optional[List[str]] = None,
        verification_method: Optional[str] = None,
        confidence: float = 0.0,
        is_direct_quote: bool = False,
    ) -> Dict[str, Any]:
        verif_id = str(uuid.uuid4())
        now = utc_now_iso()
        excerpts_json = json.dumps(supporting_excerpts) if supporting_excerpts else None
        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO verification_results (
                    id, claim_id, run_id, verdict, rationale,
                    support_score, contradiction_found, contradicting_evidence,
                    supporting_excerpts, verification_method, confidence,
                    is_direct_quote, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    verdict = excluded.verdict,
                    rationale = excluded.rationale,
                    support_score = excluded.support_score,
                    contradiction_found = excluded.contradiction_found,
                    contradicting_evidence = excluded.contradicting_evidence,
                    supporting_excerpts = excluded.supporting_excerpts,
                    verification_method = excluded.verification_method,
                    confidence = excluded.confidence,
                    is_direct_quote = excluded.is_direct_quote,
                    created_at = excluded.created_at;
                """,
                (
                    verif_id,
                    claim_id,
                    run_id,
                    verdict,
                    rationale.strip(),
                    support_score,
                    1 if contradiction_found else 0,
                    contradicting_evidence,
                    excerpts_json,
                    verification_method,
                    confidence,
                    1 if is_direct_quote else 0,
                    now,
                ),
            )
        return {
            "id": verif_id,
            "claim_id": claim_id,
            "run_id": run_id,
            "verdict": verdict,
            "rationale": rationale,
            "support_score": support_score,
            "contradiction_found": contradiction_found,
            "contradicting_evidence": contradicting_evidence,
            "supporting_excerpts": supporting_excerpts or [],
            "verification_method": verification_method,
            "confidence": confidence,
            "is_direct_quote": is_direct_quote,
            "created_at": now,
        }

    @staticmethod
    def list_by_run(run_id: str) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT vr.*, c.claim_text, c.claim_type, c.subquestion_id
                FROM verification_results vr
                JOIN claims c ON vr.claim_id = c.id
                WHERE vr.run_id = ?
                ORDER BY vr.created_at ASC;
                """,
                (run_id,),
            ).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                if item.get("supporting_excerpts"):
                    try:
                        item["supporting_excerpts"] = json.loads(item["supporting_excerpts"])
                    except Exception:
                        item["supporting_excerpts"] = []
                else:
                    item["supporting_excerpts"] = []
                results.append(item)
            return results


class RelevanceRepository:
    @staticmethod
    def record(
        source_id: str,
        run_id: str,
        research_question: str,
        relevance_score: float,
        direct_relevance: float,
        methodology_relevance: float,
        findings_relevance: float,
        domain_relevance: float,
        direct_explanation: Optional[str] = None,
        methodology_explanation: Optional[str] = None,
        findings_explanation: Optional[str] = None,
        domain_explanation: Optional[str] = None,
        decision: str = "INCLUDE",
        is_metadata_only: bool = False,
        positive_signals: Optional[List[str]] = None,
        missing_information: Optional[List[str]] = None,
        excerpts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        eval_id = str(uuid.uuid4())
        now = utc_now_iso()
        pos_json = json.dumps(positive_signals) if positive_signals else None
        miss_json = json.dumps(missing_information) if missing_information else None
        excerpts_json = json.dumps(excerpts) if excerpts else None

        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO source_relevance_evaluations (
                    id, source_id, run_id, research_question, relevance_score,
                    direct_relevance, methodology_relevance, findings_relevance, domain_relevance,
                    direct_explanation, methodology_explanation, findings_explanation, domain_explanation,
                    decision, is_metadata_only, positive_signals, missing_information, excerpts, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    eval_id,
                    source_id,
                    run_id,
                    research_question,
                    relevance_score,
                    direct_relevance,
                    methodology_relevance,
                    findings_relevance,
                    domain_relevance,
                    direct_explanation,
                    methodology_explanation,
                    findings_explanation,
                    domain_explanation,
                    decision,
                    1 if is_metadata_only else 0,
                    pos_json,
                    miss_json,
                    excerpts_json,
                    now,
                ),
            )
        return {
            "id": eval_id,
            "source_id": source_id,
            "run_id": run_id,
            "research_question": research_question,
            "relevance_score": relevance_score,
            "direct_relevance": direct_relevance,
            "methodology_relevance": methodology_relevance,
            "findings_relevance": findings_relevance,
            "domain_relevance": domain_relevance,
            "direct_explanation": direct_explanation,
            "methodology_explanation": methodology_explanation,
            "findings_explanation": findings_explanation,
            "domain_explanation": domain_explanation,
            "decision": decision,
            "is_metadata_only": is_metadata_only,
            "positive_signals": positive_signals or [],
            "missing_information": missing_information or [],
            "excerpts": excerpts or [],
            "created_at": now,
        }

    @staticmethod
    def get_by_source(source_id: str) -> Optional[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM source_relevance_evaluations WHERE source_id = ? ORDER BY created_at DESC LIMIT 1;",
                (source_id,),
            ).fetchone()
            if not row:
                return None
            item = dict(row)
            for k in ("positive_signals", "missing_information", "excerpts"):
                if item.get(k):
                    try:
                        item[k] = json.loads(item[k])
                    except Exception:
                        item[k] = []
                else:
                    item[k] = []
            return item

    @staticmethod
    def list_by_run(run_id: str) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM source_relevance_evaluations WHERE run_id = ? ORDER BY created_at ASC;",
                (run_id,),
            ).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                for k in ("positive_signals", "missing_information", "excerpts"):
                    if item.get(k):
                        try:
                            item[k] = json.loads(item[k])
                        except Exception:
                            item[k] = []
                    else:
                        item[k] = []
                results.append(item)
            return results


class PublicationClassificationRepository:
    @staticmethod
    def record(
        source_id: str,
        run_id: str,
        venue_name: Optional[str] = None,
        document_type: Optional[str] = None,
        publication_status: Optional[str] = None,
        peer_review_status: str = "UNKNOWN",
        classification_evidence: Optional[str] = None,
        metadata_source: Optional[str] = None,
        last_verified_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        class_id = str(uuid.uuid4())
        now = utc_now_iso()
        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO source_publication_classifications (
                    id, source_id, run_id, venue_name, document_type,
                    publication_status, peer_review_status, classification_evidence,
                    metadata_source, last_verified_date, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    class_id,
                    source_id,
                    run_id,
                    venue_name,
                    document_type,
                    publication_status,
                    peer_review_status,
                    classification_evidence,
                    metadata_source,
                    last_verified_date,
                    now,
                ),
            )
        return {
            "id": class_id,
            "source_id": source_id,
            "run_id": run_id,
            "venue_name": venue_name,
            "document_type": document_type,
            "publication_status": publication_status,
            "peer_review_status": peer_review_status,
            "classification_evidence": classification_evidence,
            "metadata_source": metadata_source,
            "last_verified_date": last_verified_date,
            "created_at": now,
        }

    @staticmethod
    def get_by_source(source_id: str) -> Optional[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM source_publication_classifications WHERE source_id = ? ORDER BY created_at DESC LIMIT 1;",
                (source_id,),
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_by_run(run_id: str) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM source_publication_classifications WHERE run_id = ? ORDER BY created_at ASC;",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]


class ReportRepository:
    @staticmethod
    def save(
        run_id: str,
        title: str,
        markdown_content: str,
        html_content: str,
        quality_summary: Optional[Dict[str, Any]] = None,
        citation_count: int = 0,
        verified_claim_count: int = 0,
    ) -> Dict[str, Any]:
        report_id = str(uuid.uuid4())
        now = utc_now_iso()
        quality_json = json.dumps(quality_summary) if quality_summary else None
        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO reports (
                    id, run_id, title, markdown_content, html_content,
                    quality_summary, citation_count, verified_claim_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    title = excluded.title,
                    markdown_content = excluded.markdown_content,
                    html_content = excluded.html_content,
                    quality_summary = excluded.quality_summary,
                    citation_count = excluded.citation_count,
                    verified_claim_count = excluded.verified_claim_count,
                    created_at = excluded.created_at;
                """,
                (
                    report_id,
                    run_id,
                    title.strip(),
                    markdown_content,
                    html_content,
                    quality_json,
                    citation_count,
                    verified_claim_count,
                    now,
                ),
            )
        return ReportRepository.get_by_run(run_id)  # type: ignore

    @staticmethod
    def get_by_run(run_id: str) -> Optional[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            row = conn.execute("SELECT * FROM reports WHERE run_id = ?;", (run_id,)).fetchone()
            if not row:
                return None
            report = dict(row)
            if report.get("quality_summary"):
                try:
                    report["quality_summary"] = json.loads(report["quality_summary"])
                except Exception:
                    pass
            return report


class BenchmarkRepository:
    @staticmethod
    def seed_questions(questions: List[Dict[str, Any]]) -> None:
        now = utc_now_iso()
        with db_manager.get_connection() as conn:
            for q in questions:
                subtopics_json = json.dumps(q.get("required_subtopics", []))
                criteria_json = json.dumps(q.get("criteria", {}))
                conn.execute(
                    """
                    INSERT INTO benchmark_questions (
                        id, category, question, required_subtopics,
                        expected_evidence_density, min_sources, criteria, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        category = excluded.category,
                        question = excluded.question,
                        required_subtopics = excluded.required_subtopics,
                        expected_evidence_density = excluded.expected_evidence_density,
                        min_sources = excluded.min_sources,
                        criteria = excluded.criteria;
                    """,
                    (
                        q["id"],
                        q["category"],
                        q["question"],
                        subtopics_json,
                        q.get("expected_evidence_density", 5),
                        q.get("min_sources", 3),
                        criteria_json,
                        now,
                    ),
                )

    @staticmethod
    def list_questions() -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM benchmark_questions ORDER BY category ASC, id ASC;"
            ).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["required_subtopics"] = json.loads(item["required_subtopics"])
                if item.get("criteria"):
                    item["criteria"] = json.loads(item["criteria"])
                results.append(item)
            return results

    @staticmethod
    def record_run(
        question_id: str,
        system_variant: str,
        run_id: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        error_message: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        bench_run_id = str(uuid.uuid4())
        now = utc_now_iso()
        status = "FAILED" if error_message else "COMPLETED"
        with db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO benchmark_runs (
                    id, benchmark_question_id, system_variant, run_id, status,
                    start_time, completed_time, duration_seconds, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    bench_run_id,
                    question_id,
                    system_variant,
                    run_id,
                    status,
                    now,
                    now,
                    duration_seconds,
                    error_message,
                    now,
                ),
            )
            if metrics:
                result_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO benchmark_results (
                        id, benchmark_run_id, retrieval_relevance, research_coverage,
                        claim_support_rate, citation_correctness, task_completion,
                        runtime_seconds, estimated_cost_usd, detailed_metrics, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        result_id,
                        bench_run_id,
                        metrics.get("retrieval_relevance", 0.0),
                        metrics.get("research_coverage", 0.0),
                        metrics.get("claim_support_rate", 0.0),
                        metrics.get("citation_correctness", 0.0),
                        1 if metrics.get("task_completion", True) else 0,
                        metrics.get("runtime_seconds", duration_seconds or 0.0),
                        metrics.get("estimated_cost_usd", 0.0),
                        json.dumps(metrics.get("detailed_metrics", {})),
                        now,
                    ),
                )
        return {"id": bench_run_id, "status": status}

    @staticmethod
    def list_results() -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT br.*, bq.question, bq.category,
                       bres.retrieval_relevance, bres.research_coverage,
                       bres.claim_support_rate, bres.citation_correctness,
                       bres.task_completion, bres.runtime_seconds, bres.estimated_cost_usd
                FROM benchmark_runs br
                JOIN benchmark_questions bq ON br.benchmark_question_id = bq.id
                LEFT JOIN benchmark_results bres ON br.id = bres.benchmark_run_id
                ORDER BY br.created_at DESC;
                """
            ).fetchall()
            return [dict(r) for r in rows]
