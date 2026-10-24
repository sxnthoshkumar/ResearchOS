"""
Shared Pytest Fixtures for Autonomous AI Research Assistant test suite.
"""

import os
import tempfile
import pytest

from app.database.db import DatabaseManager


@pytest.fixture
def temp_db(monkeypatch):
    """Creates an isolated temporary SQLite database for test execution."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    mgr = DatabaseManager(path)
    mgr.initialize_db()

    # monkeypatch global db_manager across all importing modules
    from app.database import db
    monkeypatch.setattr(db, "db_manager", mgr)
    from app.database import repositories
    monkeypatch.setattr(repositories, "db_manager", mgr)

    yield mgr

    try:
        os.remove(path)
    except Exception:
        pass
