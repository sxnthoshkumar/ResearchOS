"""
FastAPI Application Entrypoint for the Autonomous AI Research Assistant.
Initializes embedded SQLite database, mounts static assets, and serves the Research Dashboard.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.config import settings
from app.database.db import db_manager
from app.evaluation.benchmark import BenchmarkRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("autonomous_research_assistant")

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and benchmark questions
    logger.info("Initializing SQLite Embedded Database at %s...", settings.DATABASE_PATH)
    db_manager.initialize_db()
    BenchmarkRunner.initialize_questions()
    logger.info("Database and Benchmark suite initialized. Application ready.")
    yield
    # Shutdown
    logger.info("Application shutting down.")


app = FastAPI(
    title="Autonomous AI Research Assistant with Multi-Agent Collaboration",
    description="Multi-agent scholarly research retrieval, verification, and synthesis system.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include API routes
app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Serve the primary multi-screen research dashboard."""
    index_file = TEMPLATES_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Autonomous AI Research Assistant</h1><p>Dashboard template missing.</p>")
