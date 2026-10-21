"""
End-to-End Workflow Test: Executes a complete multi-agent research lifecycle,
verifies SQLite persistence across runs, quality gates, and benchmark comparisons.
"""

import os
import tempfile
import pytest

from app.database.db import DatabaseManager
from app.database.repositories import (
    BenchmarkRepository,
    ClaimRepository,
    EvidenceRepository,
    ProjectRepository,
    ReportRepository,
    RunRepository,
    SourceRepository,
    VerificationRepository,
)
from app.evaluation.benchmark import BenchmarkRunner
from app.orchestration.workflow import orchestrator


@pytest.fixture
def clean_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    mgr = DatabaseManager(path)
    mgr.initialize_db()
    from app.database import db, repositories
    monkeypatch.setattr(db, "db_manager", mgr)
    monkeypatch.setattr(repositories, "db_manager", mgr)
    yield mgr
    try:
        os.remove(path)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_complete_e2e_research_lifecycle(clean_db):
    # 1. User creates research project
    project = ProjectRepository.create(
        title="Comparative Inquiry: RAG vs Fine-Tuning",
        description="Comprehensive evaluation across empirical benchmarks",
    )
    assert project["id"] is not None

    # 2. User initiates research run
    run = RunRepository.create(
        project_id=project["id"],
        question="Compare Retrieval-Augmented Generation (RAG) and fine-tuning for domain-specific question answering.",
        provider_mode="demo",
        max_sources=4,
    )
    assert run["id"] is not None
    assert run["status"] == "CREATED"

    # 3. Orchestrator executes all 5 agents sequentially
    execution_result = await orchestrator.execute_run(run["id"])
    assert execution_result["status"] == "COMPLETED"
    assert execution_result.get("report_id") is not None
    assert execution_result["quality_gate"]["passed"] is True

    # 4. Verify persisted sources in SQLite
    sources = SourceRepository.list_by_run(run["id"])
    assert len(sources) >= 2
    for s in sources:
        assert s["provider"] == "demo"
        assert "[DEMO BENCHMARK]" in s["title"]
        assert s["canonical_url"] is not None

    # 5. Verify persisted evidence passages
    passages = EvidenceRepository.list_by_run(run["id"])
    assert len(passages) >= 2
    for p in passages:
        assert p["passage_text"] != ""
        assert p["extraction_method"] == "demo_synthesis"

    # 6. Verify atomic claims with evidence linkage
    claims = ClaimRepository.list_by_run(run["id"])
    assert len(claims) >= 2
    for c in claims:
        assert c["claim_text"] != ""
        assert len(c["evidence"]) >= 1

    # 7. Verify factual verification verdicts
    verifications = VerificationRepository.list_by_run(run["id"])
    assert len(verifications) >= 2
    supported_claims = [v for v in verifications if v["verdict"] == "SUPPORTED"]
    assert len(supported_claims) >= 1

    # 8. Verify canonical academic report and numbered citations
    report = ReportRepository.get_by_run(run["id"])
    assert report is not None
    assert "## Table of Contents" in report["markdown_content"]
    assert "## Executive Summary" in report["markdown_content"]
    assert "## Comparative Analysis" in report["markdown_content"]
    assert "## References" in report["markdown_content"]
    assert "<!DOCTYPE html>" in report["html_content"]


@pytest.mark.asyncio
async def test_benchmark_comparative_run(clean_db):
    BenchmarkRunner.initialize_questions()
    questions = BenchmarkRepository.list_questions()
    assert len(questions) == 20

    # Execute Baseline Run
    res_base = await BenchmarkRunner.run_benchmark_question("bq-01", "single_agent_baseline")
    assert res_base["variant"] == "single_agent_baseline"
    assert res_base["metrics"]["claim_support_rate"] < 0.50

    # Execute Five-Agent Collaborative Run
    res_collab = await BenchmarkRunner.run_benchmark_question("bq-01", "five_agent_collaborative")
    assert res_collab["variant"] == "five_agent_collaborative"
    assert res_collab["metrics"]["claim_support_rate"] >= 0.70
    assert res_collab["metrics"]["citation_correctness"] == 1.0

    # Verify both benchmark runs recorded in SQLite
    results = BenchmarkRepository.list_results()
    assert len(results) >= 2
