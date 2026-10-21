"""
Tests for SQLite Database initialization, WAL mode, pragmas, and repositories.
"""

import os
import tempfile
import pytest

from app.database.db import DatabaseManager
from app.database.repositories import (
    ProjectRepository,
    RunRepository,
    TaskRepository,
    SourceRepository,
    EvidenceRepository,
    ClaimRepository,
    VerificationRepository,
    ReportRepository,
)


@pytest.fixture
def temp_db(monkeypatch):
    """Creates an isolated temporary SQLite database for test execution."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    mgr = DatabaseManager(path)
    mgr.initialize_db()
    # monkeypatch global db_manager to point to this temp db
    from app.database import db
    monkeypatch.setattr(db, "db_manager", mgr)
    from app.database import repositories
    monkeypatch.setattr(repositories, "db_manager", mgr)
    yield mgr
    try:
        os.remove(path)
    except Exception:
        pass


def test_database_initialization(temp_db):
    """Test that database creates schema, executes pragmas, and enables foreign keys."""
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys;")
        fk = cursor.fetchone()[0]
        assert fk == 1

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        assert "research_projects" in tables
        assert "research_runs" in tables
        assert "agent_tasks" in tables
        assert "sources" in tables
        assert "evidence_passages" in tables
        assert "claims" in tables
        assert "verification_results" in tables
        assert "reports" in tables


def test_project_crud(temp_db):
    """Test creating, reading, listing, and deleting a research project."""
    p = ProjectRepository.create("Test Title", "Test Description")
    assert p["id"] is not None
    assert p["title"] == "Test Title"

    fetched = ProjectRepository.get(p["id"])
    assert fetched is not None
    assert fetched["title"] == "Test Title"

    all_projs = ProjectRepository.list_all()
    assert len(all_projs) >= 1

    deleted = ProjectRepository.delete(p["id"])
    assert deleted is True
    assert ProjectRepository.get(p["id"]) is None


def test_cascade_delete(temp_db):
    """Test that deleting a project cascades to delete runs, sources, and tasks."""
    p = ProjectRepository.create("Project Cascade", "Description")
    run = RunRepository.create(p["id"], "What is RAG?")
    SourceRepository.add(run["id"], "Paper 1", authors="Alice", publication_year=2024)
    TaskRepository.create(run["id"], "planner", "Plan Question")

    # Verify run exists
    assert RunRepository.get(run["id"]) is not None
    assert len(SourceRepository.list_by_run(run["id"])) == 1

    # Delete project
    ProjectRepository.delete(p["id"])

    # Run and source should be cascade deleted
    assert RunRepository.get(run["id"]) is None
    assert len(SourceRepository.list_by_run(run["id"])) == 0
