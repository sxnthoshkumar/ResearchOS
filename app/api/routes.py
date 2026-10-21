"""
FastAPI REST & Server-Sent Events Route Handlers for the Autonomous AI Research Assistant.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.database.repositories import (
    BenchmarkRepository,
    ClaimRepository,
    EvidenceRepository,
    ProjectRepository,
    PublicationClassificationRepository,
    RelevanceRepository,
    ReportRepository,
    RunRepository,
    SourceRepository,
    TaskRepository,
    VerificationRepository,
)
from app.evaluation.benchmark import BenchmarkRunner
from app.evaluation.metrics import (
    calculate_citation_provenance_metrics,
    calculate_claim_quality_metrics,
    calculate_publication_classification_metrics,
    calculate_relevance_metrics,
)
from app.orchestration.events import broadcaster
from app.orchestration.workflow import orchestrator

router = APIRouter(prefix="/api")


# --- Schemas ---

class CreateProjectRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)


class StartRunRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=1000)
    provider_mode: Optional[str] = None  # 'demo', 'openai', or None for system default
    search_providers: Optional[List[str]] = Field(default_factory=lambda: ["openalex", "arxiv"])
    max_sources: int = Field(default=8, ge=2, le=30)


class RunBenchmarkRequest(BaseModel):
    question_id: str
    system_variant: str = "five_agent_collaborative"  # or 'single_agent_baseline'


# --- System Status & Health ---

@router.get("/status")
async def get_system_status() -> Dict[str, Any]:
    public_status = settings.get_public_status()
    ollama_health = None

    # Check Ollama connectivity if configured or requested
    if settings.LLM_PROVIDER.lower() == "ollama":
        from app.llm.ollama_provider import OllamaLLMProvider
        provider = OllamaLLMProvider()
        ollama_health = await provider.check_health()

    return {
        "status": "online",
        "llm": public_status,
        "ollama": ollama_health,
        "ollama_health": ollama_health,
        "database": {"path": settings.DATABASE_PATH, "fts5_active": True},
    }


@router.get("/health/ollama")
async def get_ollama_health() -> Dict[str, Any]:
    """Dedicated health check endpoint for local Ollama service."""
    from app.llm.ollama_provider import OllamaLLMProvider
    provider = OllamaLLMProvider()
    return await provider.check_health()


# --- Projects ---

@router.get("/projects")
def list_projects() -> List[Dict[str, Any]]:
    return ProjectRepository.list_all()


@router.post("/projects")
def create_project(req: CreateProjectRequest) -> Dict[str, Any]:
    return ProjectRepository.create(title=req.title, description=req.description)


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> Dict[str, Any]:
    p = ProjectRepository.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    runs = RunRepository.list_by_project(project_id)
    p["runs"] = runs
    return p


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> Dict[str, Any]:
    success = ProjectRepository.delete(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found or already deleted")
    return {"status": "deleted", "project_id": project_id}


# --- Research Runs & Execution ---

@router.post("/projects/{project_id}/run")
async def start_research_run(
    project_id: str, req: StartRunRequest, background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    p = ProjectRepository.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    provider_mode = req.provider_mode if req.provider_mode else "live"
    providers_str = ",".join(req.search_providers) if req.search_providers else "openalex,arxiv"

    active_model = settings.get_active_model_name() if provider_mode != "demo" else "demo-deterministic-engine"

    run = RunRepository.create(
        project_id=project_id,
        question=req.question,
        provider_mode=provider_mode,
        model_name=active_model,
        search_providers=providers_str,
        max_sources=req.max_sources,
    )

    # Launch orchestrator in background task
    background_tasks.add_task(orchestrator.execute_run, run["id"])

    return run


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    run = RunRepository.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    tasks = TaskRepository.list_by_run(run_id)
    sources = SourceRepository.list_by_run(run_id)
    claims = ClaimRepository.list_by_run(run_id)
    verifs = VerificationRepository.list_by_run(run_id)
    report = ReportRepository.get_by_run(run_id)
    relevances = RelevanceRepository.list_by_run(run_id)
    pub_classes = PublicationClassificationRepository.list_by_run(run_id)

    run["tasks"] = tasks
    run["source_count"] = len(sources)
    run["claim_count"] = len(claims)
    run["verified_count"] = len([v for v in verifs if v.get("verdict") == "SUPPORTED"])
    run["has_report"] = report is not None

    # Relevance and publication breakdown
    run["included_sources_count"] = sum(1 for r in relevances if r.get("decision") == "INCLUDE")
    run["reviewed_sources_count"] = sum(1 for r in relevances if r.get("decision") == "REVIEW")
    run["excluded_sources_count"] = sum(1 for r in relevances if r.get("decision") == "EXCLUDE")
    run["peer_reviewed_count"] = sum(
        1 for p in pub_classes if p.get("peer_review_status") in ("PEER_REVIEWED_JOURNAL", "PEER_REVIEWED_CONFERENCE")
    )
    run["preprint_count"] = sum(1 for p in pub_classes if p.get("peer_review_status") == "PREPRINT")
    run["unknown_pub_count"] = sum(1 for p in pub_classes if p.get("peer_review_status") == "UNKNOWN")
    return run


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> Dict[str, Any]:
    success = orchestrator.cancel_run(run_id)
    if not success:
        raise HTTPException(status_code=400, detail="Run cannot be cancelled or is already finished")
    return {"status": "cancelling", "run_id": run_id}


@router.get("/runs/{run_id}/events")
async def stream_run_events(run_id: str) -> StreamingResponse:
    """Server-Sent Events endpoint streaming real-time execution progress."""
    run = RunRepository.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return StreamingResponse(
        broadcaster.subscribe(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Detailed Run Artifacts ---

@router.get("/runs/{run_id}/tasks")
def list_run_tasks(run_id: str) -> List[Dict[str, Any]]:
    return TaskRepository.list_by_run(run_id)


@router.get("/runs/{run_id}/sources")
def list_run_sources(run_id: str) -> List[Dict[str, Any]]:
    sources = SourceRepository.list_by_run(run_id)
    relevances = {r["source_id"]: r for r in RelevanceRepository.list_by_run(run_id)}
    pub_classes = {p["source_id"]: p for p in PublicationClassificationRepository.list_by_run(run_id)}
    enriched = []
    for s in sources:
        item = dict(s)
        item["relevance"] = relevances.get(s["id"])
        item["publication_classification"] = pub_classes.get(s["id"])
        enriched.append(item)
    return enriched


@router.get("/runs/{run_id}/metrics")
def get_run_validation_metrics(run_id: str) -> Dict[str, Any]:
    """Returns comprehensive scientific reliability and evidence validation metrics."""
    sources = SourceRepository.list_by_run(run_id)
    relevances = RelevanceRepository.list_by_run(run_id)
    claims = ClaimRepository.list_by_run(run_id)
    passages = EvidenceRepository.list_by_run(run_id)
    verifs = VerificationRepository.list_by_run(run_id)
    pub_classes = PublicationClassificationRepository.list_by_run(run_id)
    report = ReportRepository.get_by_run(run_id)
    md_content = report.get("markdown_content", "") if report else ""

    relevance_m = calculate_relevance_metrics(relevances, len(sources))
    cit_prov_m = calculate_citation_provenance_metrics(md_content, sources, claims, passages)
    claim_m = calculate_claim_quality_metrics(claims, verifs)
    pub_m = calculate_publication_classification_metrics(pub_classes, len(sources))

    return {
        "run_id": run_id,
        "relevance": relevance_m,
        "citation_provenance": cit_prov_m,
        "claims": claim_m,
        "publication": pub_m,
    }


@router.get("/runs/{run_id}/evidence")
def list_run_evidence(run_id: str) -> List[Dict[str, Any]]:
    return EvidenceRepository.list_by_run(run_id)


@router.get("/runs/{run_id}/claims")
def list_run_claims(run_id: str) -> List[Dict[str, Any]]:
    claims = ClaimRepository.list_by_run(run_id)
    verifs = VerificationRepository.list_by_run(run_id)
    verif_map = {v["claim_id"]: v for v in verifs}
    for c in claims:
        c["verification"] = verif_map.get(c["id"])
    return claims


@router.get("/runs/{run_id}/report")
def get_run_report(run_id: str) -> Dict[str, Any]:
    report = ReportRepository.get_by_run(run_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not generated yet for this run")
    return report


@router.get("/runs/{run_id}/export/markdown")
def export_report_markdown(run_id: str) -> PlainTextResponse:
    report = ReportRepository.get_by_run(run_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    filename = f"research_report_{run_id[:8]}.md"
    return PlainTextResponse(
        report["markdown_content"],
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/runs/{run_id}/export/html")
def export_report_html(run_id: str) -> HTMLResponse:
    report = ReportRepository.get_by_run(run_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    filename = f"research_report_{run_id[:8]}.html"
    return HTMLResponse(
        report["html_content"],
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --- Benchmark Suite ---

@router.get("/benchmarks/questions")
def list_benchmark_questions() -> List[Dict[str, Any]]:
    BenchmarkRunner.initialize_questions()
    return BenchmarkRepository.list_questions()


@router.post("/benchmarks/run")
async def run_benchmark_test(req: RunBenchmarkRequest) -> Dict[str, Any]:
    BenchmarkRunner.initialize_questions()
    result = await BenchmarkRunner.run_benchmark_question(
        question_id=req.question_id, system_variant=req.system_variant
    )
    return result


@router.get("/benchmarks/results")
def list_benchmark_results() -> List[Dict[str, Any]]:
    return BenchmarkRepository.list_results()
