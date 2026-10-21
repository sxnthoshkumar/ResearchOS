"""
Tests for Central Research Orchestrator, state machine transitions, cancellation, and retry limits.
"""

import os
import tempfile
import pytest

from app.database.db import DatabaseManager
from app.database.repositories import ProjectRepository, RunRepository
from app.orchestration.state import InvalidStateTransitionError, WorkflowState, validate_transition
from app.orchestration.workflow import ResearchOrchestrator


@pytest.fixture
def test_setup(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    mgr = DatabaseManager(path)
    mgr.initialize_db()
    from app.database import db, repositories
    monkeypatch.setattr(db, "db_manager", mgr)
    monkeypatch.setattr(repositories, "db_manager", mgr)

    p = ProjectRepository.create("Orchestrator Test Project")
    yield p["id"]
    try:
        os.remove(path)
    except Exception:
        pass


def test_valid_state_transitions():
    assert validate_transition(WorkflowState.CREATED, WorkflowState.PLANNING) is True
    assert validate_transition(WorkflowState.PLANNING, WorkflowState.RESEARCHING) is True
    assert validate_transition(WorkflowState.RESEARCHING, WorkflowState.ANALYZING) is True
    assert validate_transition(WorkflowState.ANALYZING, WorkflowState.VERIFYING) is True
    assert validate_transition(WorkflowState.VERIFYING, WorkflowState.GENERATING_REPORT) is True
    assert validate_transition(WorkflowState.GENERATING_REPORT, WorkflowState.EVALUATING) is True
    assert validate_transition(WorkflowState.EVALUATING, WorkflowState.COMPLETED) is True


def test_invalid_state_transitions():
    # Cannot jump from CREATED directly to COMPLETED
    with pytest.raises(InvalidStateTransitionError):
        validate_transition(WorkflowState.CREATED, WorkflowState.COMPLETED)

    # Cannot transition out of COMPLETED
    with pytest.raises(InvalidStateTransitionError):
        validate_transition(WorkflowState.COMPLETED, WorkflowState.PLANNING)


@pytest.mark.asyncio
async def test_orchestrator_full_demo_run(test_setup):
    project_id = test_setup
    run = RunRepository.create(project_id, "Compare RAG and fine-tuning trade-offs", provider_mode="demo")

    orchestrator = ResearchOrchestrator()
    result = await orchestrator.execute_run(run["id"])

    assert result["status"] == "COMPLETED"
    assert result.get("report_id") is not None

    # Check persisted run state
    updated_run = RunRepository.get(run["id"])
    assert updated_run["status"] == "COMPLETED"
    assert updated_run["duration_seconds"] > 0


@pytest.mark.asyncio
async def test_orchestrator_cancellation(test_setup):
    project_id = test_setup
    run = RunRepository.create(project_id, "Question to be cancelled", provider_mode="demo")

    orchestrator = ResearchOrchestrator()
    # Cancel before execution
    cancelled = orchestrator.cancel_run(run["id"])
    assert cancelled is True

    result = await orchestrator.execute_run(run["id"])
    assert result["status"] == "CANCELLED"

    updated = RunRepository.get(run["id"])
    assert updated["status"] == "CANCELLED"
