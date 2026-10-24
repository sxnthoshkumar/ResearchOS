"""
Embedded SQLite Database connection manager, migration engine, and FTS5 handler.
Uses Python's standard sqlite3 module with WAL mode and robust concurrency configuration.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/research_assistant.db")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class DatabaseManager:
    """Manages SQLite connections, schema initialization, and full-text search."""

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            db_path = os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH))
        self.db_path = Path(db_path)
        self._fts_available: Optional[bool] = None

    def initialize_db(self) -> None:
        """Create parent directory, execute schema migrations, configure PRAGMAs, and setup FTS5."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as conn:
            # Concurrency & integrity pragmas
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 10000;")

            # Execute base schema
            if SCHEMA_PATH.exists():
                schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
                conn.executescript(schema_sql)
            else:
                logger.error("schema.sql not found at %s", SCHEMA_PATH)
                raise FileNotFoundError(f"Schema missing: {SCHEMA_PATH}")

            # Run migrations on existing tables
            self._run_migrations(conn)

            # Check and setup FTS5 or fallback
            self._setup_full_text_search(conn)
            self._record_schema_version(conn, "1.1.0")

        logger.info("Database initialized successfully at %s", self.db_path)

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """Add any missing columns to existing tables without data loss."""
        cursor = conn.cursor()

        # 1. verification_results migrations
        cursor.execute("PRAGMA table_info(verification_results);")
        vr_columns = {row["name"] for row in cursor.fetchall()}
        needed_vr = {
            "contradicting_evidence": "TEXT",
            "supporting_excerpts": "TEXT",
            "verification_method": "TEXT",
            "confidence": "REAL DEFAULT 0.0",
            "is_direct_quote": "INTEGER NOT NULL DEFAULT 0",
        }
        for col, col_type in needed_vr.items():
            if col not in vr_columns:
                try:
                    conn.execute(f"ALTER TABLE verification_results ADD COLUMN {col} {col_type};")
                    logger.info("Migrated verification_results: added column %s", col)
                except sqlite3.OperationalError as e:
                    logger.debug("Column migration note: %s", e)

        # 2. research_projects migrations (status)
        cursor.execute("PRAGMA table_info(research_projects);")
        proj_columns = {row["name"] for row in cursor.fetchall()}
        if "status" not in proj_columns:
            try:
                conn.execute("ALTER TABLE research_projects ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE';")
                logger.info("Migrated research_projects: added column status")
            except sqlite3.OperationalError as e:
                logger.debug("Column migration note for research_projects: %s", e)

        # 3. research_runs migrations (domain, publication_preference, evidence_preference, relevance_threshold)
        cursor.execute("PRAGMA table_info(research_runs);")
        run_columns = {row["name"] for row in cursor.fetchall()}
        needed_run_cols = {
            "domain": "TEXT DEFAULT 'Computer Science'",
            "publication_preference": "TEXT DEFAULT 'all'",
            "evidence_preference": "TEXT DEFAULT 'full_text_preferred'",
            "relevance_threshold": "REAL DEFAULT 50.0",
        }
        for col, col_def in needed_run_cols.items():
            if col not in run_columns:
                try:
                    conn.execute(f"ALTER TABLE research_runs ADD COLUMN {col} {col_def};")
                    logger.info("Migrated research_runs: added column %s", col)
                except sqlite3.OperationalError as e:
                    logger.debug("Column migration note for research_runs: %s", e)

        # 4. research_syntheses table creation
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_syntheses (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                contributing_run_ids TEXT NOT NULL,
                markdown_content TEXT NOT NULL,
                html_content TEXT NOT NULL,
                citation_count INTEGER NOT NULL DEFAULT 0,
                conflict_count INTEGER NOT NULL DEFAULT 0,
                conflicts_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE
            );
            """
        )


    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing a configured SQLite connection with row factory."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False,
            isolation_level=None  # autocommit mode; explicit transactions handled with BEGIN
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        try:
            yield conn
        finally:
            conn.close()

    def _setup_full_text_search(self, conn: sqlite3.Connection) -> None:
        """Attempt to configure FTS5 for evidence passages, with graceful fallback to standard LIKE."""
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(evidence_id, passage_text);")
            self._fts_available = True
            logger.info("SQLite FTS5 full-text search index active.")
        except sqlite3.OperationalError as e:
            logger.warning("SQLite FTS5 not available in runtime (%s). Fallback to standard search.", e)
            self._fts_available = False

    def is_fts_available(self) -> bool:
        if self._fts_available is None:
            with self.get_connection() as conn:
                self._setup_full_text_search(conn)
        return bool(self._fts_available)

    def _record_schema_version(self, conn: sqlite3.Connection, version: str) -> None:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('schema_version', ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;
            """,
            (version,)
        )


# Global instance
db_manager = DatabaseManager()
