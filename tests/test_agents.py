"""
Unit tests for all Five Specialized Agents using the deterministic Demo LLM Provider.
"""

import os
import tempfile
import pytest

from app.agents.planner import PlannerAgent
from app.agents.researcher import ResearchAgent
from app.agents.analyst import AnalysisAgent
from app.agents.fact_checker import FactCheckingAgent
from app.agents.report_writer import ReportWriterAgent
from app.database.db import DatabaseManager
from app.database.repositories import ProjectRepository, RunRepository
from app.llm.demo_provider import DemoLLMProvider


@pytest.fixture
def test_env(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    mgr = DatabaseManager(path)
    mgr.initialize_db()
    from app.database import db, repositories
    monkeypatch.setattr(db, "db_manager", mgr)
    monkeypatch.setattr(repositories, "db_manager", mgr)

    p = ProjectRepository.create("Test MultiAgent Project", "Testing all 5 agents")
    run = RunRepository.create(p["id"], "Compare RAG and fine-tuning for domain-specific QA")
    yield run["id"]
    try:
        os.remove(path)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_agent_1_planner():
    llm = DemoLLMProvider()
    planner = PlannerAgent(llm)

    # Question validation checks
    assert planner.validate_question("") is not None
    assert planner.validate_question("Too short") is not None
    assert planner.validate_question("Valid comprehensive research question for evaluation") is None

    # Plan creation
    plan = await planner.create_plan("Evaluate consensus algorithms in Byzantine fault-tolerant systems")
    assert plan.plan_id is not None
    assert len(plan.subquestions) >= 3
    assert len(plan.target_sections) >= 4
    for sq in plan.subquestions:
        assert len(sq.search_queries) >= 1
        assert sq.expected_evidence != ""


@pytest.mark.asyncio
async def test_agent_2_researcher(test_env):
    run_id = test_env
    llm = DemoLLMProvider()
    planner = PlannerAgent(llm)
    plan = await planner.create_plan("Evaluate consensus algorithms in Byzantine fault-tolerant systems")

    researcher = ResearchAgent()
    harvest = await researcher.execute_plan(run_id, plan, is_demo=True, max_sources=4)

    assert harvest.total_sources >= 2
    assert harvest.total_passages >= 2
    assert len(harvest.subquestion_harvests) >= 1


@pytest.mark.asyncio
async def test_agent_3_analyst(test_env):
    run_id = test_env
    llm = DemoLLMProvider()

    # Pre-populate research harvest in demo mode
    planner = PlannerAgent(llm)
    plan = await planner.create_plan("Evaluate consensus algorithms in Byzantine fault-tolerant systems")
    researcher = ResearchAgent()
    await researcher.execute_plan(run_id, plan, is_demo=True)

    analyst = AnalysisAgent(llm)
    analysis_res = await analyst.analyze(run_id, "Evaluate consensus algorithms in Byzantine fault-tolerant systems")

    assert analysis_res.total_claims >= 2
    assert len(analysis_res.claims) >= 2
    for c in analysis_res.claims:
        assert c.claim_text != ""
        assert len(c.evidence_ids) >= 1


@pytest.mark.asyncio
async def test_agent_4_fact_checker(test_env):
    run_id = test_env
    llm = DemoLLMProvider()

    planner = PlannerAgent(llm)
    plan = await planner.create_plan("Evaluate consensus algorithms in Byzantine fault-tolerant systems")
    researcher = ResearchAgent()
    await researcher.execute_plan(run_id, plan, is_demo=True)
    analyst = AnalysisAgent(llm)
    await analyst.analyze(run_id, "Evaluate consensus algorithms in Byzantine fault-tolerant systems")

    fact_checker = FactCheckingAgent(llm)
    audit_res = await fact_checker.verify_claims(run_id, retry_budget_remaining=2)

    assert audit_res.total_claims_audited >= 2
    for audit in audit_res.audits:
        assert audit.verdict in {
            "SUPPORTED",
            "PARTIALLY_SUPPORTED",
            "UNSUPPORTED",
            "CONFLICTING",
            "NOT_CHECKABLE",
        }
        assert audit.rationale != ""


@pytest.mark.asyncio
async def test_agent_5_report_writer(test_env):
    run_id = test_env
    llm = DemoLLMProvider()

    planner = PlannerAgent(llm)
    plan = await planner.create_plan("Evaluate consensus algorithms in Byzantine fault-tolerant systems")
    researcher = ResearchAgent()
    await researcher.execute_plan(run_id, plan, is_demo=True)
    analyst = AnalysisAgent(llm)
    await analyst.analyze(run_id, "Evaluate consensus algorithms in Byzantine fault-tolerant systems")
    fact_checker = FactCheckingAgent(llm)
    await fact_checker.verify_claims(run_id, retry_budget_remaining=2)

    report_writer = ReportWriterAgent(llm)
    rep_res = await report_writer.generate_report(run_id, "Evaluate consensus algorithms in Byzantine fault-tolerant systems", is_demo=True)

    assert rep_res.report_id is not None
    assert "## Executive Summary" in rep_res.markdown_content
    assert "## Methodology" in rep_res.markdown_content
    assert "## Limitations & Failure Modes" in rep_res.markdown_content
    assert "## References" in rep_res.markdown_content
    assert "[1]" in rep_res.markdown_content
    assert rep_res.quality_gate.passed is True
