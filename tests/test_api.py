"""
Tests for FastAPI HTTP routes, SSE endpoint availability, and report exports.
"""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.db import DatabaseManager


@pytest.fixture
def client(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    mgr = DatabaseManager(path)
    mgr.initialize_db()
    from app.database import db, repositories
    monkeypatch.setattr(db, "db_manager", mgr)
    monkeypatch.setattr(repositories, "db_manager", mgr)

    with TestClient(app) as test_client:
        yield test_client

    try:
        os.remove(path)
    except Exception:
        pass


def test_root_dashboard(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Autonomous AI Research Assistant" in res.text


def test_system_status_endpoint(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "llm" in data
    assert "database" in data
    assert "masked_key" in data["llm"]


def test_project_endpoints(client):
    # 1. Create project
    create_res = client.post(
        "/api/projects",
        json={"title": "Test Web Project", "description": "API test desc"},
    )
    assert create_res.status_code == 200
    p = create_res.json()
    assert p["id"] is not None
    assert p["title"] == "Test Web Project"

    # 2. List projects
    list_res = client.get("/api/projects")
    assert list_res.status_code == 200
    projs = list_res.json()
    assert any(item["id"] == p["id"] for item in projs)

    # 3. Get single project
    get_res = client.get(f"/api/projects/{p['id']}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Test Web Project"

    # 4. Delete project
    del_res = client.delete(f"/api/projects/{p['id']}")
    assert del_res.status_code == 200
    assert client.get(f"/api/projects/{p['id']}").status_code == 404


def test_benchmark_endpoints(client):
    q_res = client.get("/api/benchmarks/questions")
    assert q_res.status_code == 200
    questions = q_res.json()
    assert len(questions) >= 20
    assert any(q["id"] == "bq-01" for q in questions)
