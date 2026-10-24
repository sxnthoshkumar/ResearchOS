"""
Tests for Project Workspace Management, Safe Deletion, Archive/Restore,
Project Source Library Aggregation, and Multi-Run Synthesis.
"""

import pytest
from app.database.repositories import (
    ClaimRepository,
    EvidenceRepository,
    ProjectRepository,
    ReportRepository,
    RunRepository,
    SourceRepository,
    SynthesisRepository,
    VerificationRepository,
)
from app.research.synthesis import SynthesisEngine


@pytest.fixture
def workspace_project(temp_db):
    """Creates a clean project for testing."""
    p = ProjectRepository.create(
        title="RAG Systems Evaluation Workspace",
        description="A multi-run study comparing RAG architectures and fine-tuning trade-offs.",
    )
    return p


def test_project_lifecycle_and_archival(workspace_project):
    """Tests project creation, rename, update description, archive, and restore."""
    pid = workspace_project["id"]
    assert workspace_project["status"] == "ACTIVE"

    # 1. Update title and description
    updated = ProjectRepository.update(
        pid,
        title="RAG & Fine-Tuning Academic Benchmark",
        description="Updated research scope.",
    )
    assert updated["title"] == "RAG & Fine-Tuning Academic Benchmark"
    assert updated["description"] == "Updated research scope."

    # 2. Archive
    archived = ProjectRepository.archive(pid)
    assert archived["status"] == "ARCHIVED"

    # Listing active-only should exclude archived
    active_only = ProjectRepository.list_all(include_archived=False)
    assert not any(p["id"] == pid for p in active_only)

    all_projs = ProjectRepository.list_all(include_archived=True)
    assert any(p["id"] == pid and p["status"] == "ARCHIVED" for p in all_projs)

    # 3. Restore
    restored = ProjectRepository.restore(pid)
    assert restored["status"] == "ACTIVE"
    active_after = ProjectRepository.list_all(include_archived=False)
    assert any(p["id"] == pid for p in active_after)


def test_project_stats_and_safe_delete(workspace_project):
    """Tests that project stats track runs, sources, and deletion reports dependent count."""
    pid = workspace_project["id"]

    # Create 2 runs
    r1 = RunRepository.create(pid, "What is RAG architecture?", domain="Computer Science")
    r2 = RunRepository.create(pid, "What are RAG limitations?", domain="Computer Science")

    # Add sources to r1 and r2
    SourceRepository.add(r1["id"], "Source A", doi="10.1000/a")
    SourceRepository.add(r2["id"], "Source B", doi="10.1000/b")

    stats = ProjectRepository.get_stats(pid)
    assert stats["runs_count"] == 2
    assert stats["sources_count"] == 2

    # Safe delete with details
    del_res = ProjectRepository.delete_with_details(pid)
    assert del_res["success"] is True
    assert del_res["deleted_runs_count"] == 2
    assert del_res["deleted_sources_count"] == 2

    assert ProjectRepository.get(pid) is None
    assert RunRepository.get(r1["id"]) is None
    assert RunRepository.get(r2["id"]) is None


def test_project_sources_aggregation_and_deduplication(workspace_project):
    """Tests that SourceRepository.list_by_project aggregates and deduplicates sources with provenance."""
    pid = workspace_project["id"]

    r1 = RunRepository.create(pid, "Run 1", domain="Computer Science")
    r2 = RunRepository.create(pid, "Run 2", domain="Computer Science")

    # Both runs cite the same paper with the same DOI
    SourceRepository.add(
        r1["id"],
        title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        authors="Lewis et al.",
        publication_year=2020,
        doi="10.48550/arXiv.2005.11401",
    )
    SourceRepository.add(
        r2["id"],
        title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        authors="Lewis et al.",
        publication_year=2020,
        doi="10.48550/arXiv.2005.11401",
    )
    # r2 also cites a second unique paper
    SourceRepository.add(
        r2["id"],
        title="Benchmarking Large Language Models",
        authors="Smith et al.",
        publication_year=2023,
        doi="10.1000/benchmark2023",
    )

    project_sources = SourceRepository.list_by_project(pid)
    assert len(project_sources) == 2  # Deduplicated from 3 total source records

    # The Lewis paper should note that it was cited in both Run 1 and Run 2
    lewis_source = next(s for s in project_sources if "Lewis" in s.get("authors", ""))
    assert len(lewis_source["contributing_runs"]) == 2
    contributing_run_ids = {cr["run_id"] for cr in lewis_source["contributing_runs"]}
    assert r1["id"] in contributing_run_ids
    assert r2["id"] in contributing_run_ids


def test_multi_run_synthesis_generation(workspace_project):
    """Tests that SynthesisEngine combines 2 runs, detects consensus & conflicts, and preserves reports."""
    pid = workspace_project["id"]

    # Setup Run 1
    r1 = RunRepository.create(pid, "What is RAG?", domain="Computer Science")
    s1 = SourceRepository.add(r1["id"], "RAG Foundations", doi="10.1000/rag1", authors="Alice et al.")
    ev1 = EvidenceRepository.add(s1["id"], r1["id"], "RAG reduces factual hallucinations by grounding generation.")
    c1 = ClaimRepository.add(r1["id"], "RAG architectures reduce factual hallucinations in domain QA.")
    ClaimRepository.link_evidence(c1["id"], ev1["id"])
    VerificationRepository.record(c1["id"], r1["id"], "SUPPORTED", rationale="Confirmed by passage.")
    ReportRepository.save(
        r1["id"],
        title="RAG Foundations Report",
        markdown_content="# RAG Foundations\nRAG reduces hallucinations.",
        html_content="<h1>RAG Foundations</h1><p>RAG reduces hallucinations.</p>",
    )

    # Setup Run 2 with complementary and contrasting claim on cost
    r2 = RunRepository.create(pid, "What are the trade-offs of fine-tuning?", domain="Computer Science")
    s2 = SourceRepository.add(r2["id"], "Fine-Tuning Costs", doi="10.1000/ft2", authors="Bob et al.")
    ev2 = EvidenceRepository.add(s2["id"], r2["id"], "Fine-tuning incurs higher initial training cost however offers lower latency at inference.")
    c2 = ClaimRepository.add(r2["id"], "Fine-tuning incurs higher training cost however minimizes inference latency compared to RAG vector lookups.")
    ClaimRepository.link_evidence(c2["id"], ev2["id"])
    VerificationRepository.record(c2["id"], r2["id"], "SUPPORTED", rationale="Confirmed by benchmark.")
    ReportRepository.save(
        r2["id"],
        title="Fine-Tuning Trade-offs Report",
        markdown_content="# Fine-Tuning Trade-offs\nFine-tuning incurs higher training cost.",
        html_content="<h1>Fine-Tuning Trade-offs</h1><p>Fine-tuning incurs higher training cost.</p>",
    )

    # Generate synthesis
    synthesis = SynthesisEngine.create_synthesis(
        project_id=pid,
        run_ids=[r1["id"], r2["id"]],
        custom_title="Comparative Synthesis: RAG vs Fine-Tuning",
    )

    assert synthesis is not None
    assert synthesis["title"] == "Comparative Synthesis: RAG vs Fine-Tuning"
    assert synthesis["project_id"] == pid
    assert len(synthesis["contributing_run_ids"]) == 2
    assert synthesis["citation_count"] == 2
    assert "Contributing Inquiries Overview" in synthesis["markdown_content"]
    assert "Cross-Run Evidence & Claim Verification Matrix" in synthesis["markdown_content"]
    assert "Consolidated References" in synthesis["markdown_content"]
    assert "RAG Foundations" in synthesis["markdown_content"]
    assert "Fine-Tuning Costs" in synthesis["markdown_content"]

    # Verify that individual run reports were NOT overwritten
    rep1 = ReportRepository.get_by_run(r1["id"])
    assert rep1["title"] == "RAG Foundations Report"
    assert "# RAG Foundations" in rep1["markdown_content"]

    rep2 = ReportRepository.get_by_run(r2["id"])
    assert rep2["title"] == "Fine-Tuning Trade-offs Report"
    assert "# Fine-Tuning Trade-offs" in rep2["markdown_content"]

    # Verify listing syntheses by project
    syntheses_list = SynthesisRepository.list_by_project(pid)
    assert len(syntheses_list) == 1
    assert syntheses_list[0]["id"] == synthesis["id"]


def test_synthesis_validation_errors(workspace_project):
    """Tests that synthesis fails gracefully on insufficient runs or cross-project runs."""
    pid = workspace_project["id"]

    # 1. Less than 2 runs
    with pytest.raises(ValueError, match="at least 2"):
        SynthesisEngine.create_synthesis(pid, ["only-one-id"])

    # 2. Run belonging to another project
    other_proj = ProjectRepository.create("Other Project")
    other_run = RunRepository.create(other_proj["id"], "Other Question")
    ReportRepository.save(other_run["id"], "Other Report", "Content", "<p>Content</p>")

    r1 = RunRepository.create(pid, "Valid Run")
    ReportRepository.save(r1["id"], "Valid Report", "Content", "<p>Content</p>")

    with pytest.raises(ValueError, match="different project"):
        SynthesisEngine.create_synthesis(pid, [r1["id"], other_run["id"]])


def test_run_configuration_persistence_and_isolation(workspace_project):
    """Verifies that each research run preserves its exact domain, source cap, repositories,
    and advanced preferences without mutability or bleed between runs."""
    pid = workspace_project["id"]

    # 1. Create first run with explicit custom configuration
    r1 = RunRepository.create(
        project_id=pid,
        question="What are the off-target prediction accuracies of CRISPR deep learning models?",
        domain="Bioinformatics & Genomics",
        provider_mode="demo",
        model_name="demo-deterministic-engine",
        search_providers="openalex",
        max_sources=12,
        publication_preference="peer_reviewed_only",
        evidence_preference="full_text_required",
        relevance_threshold=65.0,
        max_retries=3,
    )

    saved_r1 = RunRepository.get(r1["id"])
    assert saved_r1 is not None
    assert saved_r1["question"] == "What are the off-target prediction accuracies of CRISPR deep learning models?"
    assert saved_r1["domain"] == "Bioinformatics & Genomics"
    assert saved_r1["max_sources"] == 12
    assert saved_r1["search_providers"] == "openalex"
    assert saved_r1["provider_mode"] == "demo"
    assert saved_r1["publication_preference"] == "peer_reviewed_only"
    assert saved_r1["evidence_preference"] == "full_text_required"
    assert saved_r1["relevance_threshold"] == 65.0
    assert saved_r1["max_retries"] == 3

    # 2. Create second run with completely different settings in the same workspace
    r2 = RunRepository.create(
        project_id=pid,
        question="How do superconducting qubits scale error mitigation using surface codes?",
        domain="Quantum Physics",
        provider_mode="ollama",
        model_name="qwen2.5:3b",
        search_providers="arxiv",
        max_sources=5,
        publication_preference="preprints_preferred",
        evidence_preference="abstract_only",
        relevance_threshold=40.0,
        max_retries=1,
    )

    saved_r2 = RunRepository.get(r2["id"])
    assert saved_r2 is not None
    assert saved_r2["domain"] == "Quantum Physics"
    assert saved_r2["max_sources"] == 5
    assert saved_r2["search_providers"] == "arxiv"
    assert saved_r2["provider_mode"] == "ollama"
    assert saved_r2["publication_preference"] == "preprints_preferred"
    assert saved_r2["evidence_preference"] == "abstract_only"
    assert saved_r2["relevance_threshold"] == 40.0
    assert saved_r2["max_retries"] == 1

    # 3. Confirm that earlier run r1 was NOT mutated
    re_r1 = RunRepository.get(r1["id"])
    assert re_r1["domain"] == "Bioinformatics & Genomics"
    assert re_r1["max_sources"] == 12
    assert re_r1["search_providers"] == "openalex"
    assert re_r1["publication_preference"] == "peer_reviewed_only"
    assert re_r1["evidence_preference"] == "full_text_required"
    assert re_r1["relevance_threshold"] == 65.0
    assert re_r1["max_retries"] == 3


def test_api_start_run_validation_and_configuration(workspace_project):
    """Tests the /api/projects/{id}/run endpoint for input validation and configuration persistence."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    pid = workspace_project["id"]

    # 1. Validation: question too short
    res_short = client.post(
        f"/api/projects/{pid}/run",
        json={"question": "Why?"},
    )
    assert res_short.status_code == 422

    # 2. Validation: no search providers
    res_noprov = client.post(
        f"/api/projects/{pid}/run",
        json={"question": "Valid academic query for evaluation?", "search_providers": []},
    )
    assert res_noprov.status_code == 400

    # 3. Validation: max_sources out of range
    res_oor = client.post(
        f"/api/projects/{pid}/run",
        json={"question": "Valid academic query for evaluation?", "max_sources": 50},
    )
    assert res_oor.status_code == 422

    # 4. Successful creation with full configuration
    res_ok = client.post(
        f"/api/projects/{pid}/run",
        json={
            "question": "How do topological quantum materials compare with superconducting qubits?",
            "domain": "Condensed Matter Physics",
            "provider_mode": "demo",
            "search_providers": ["openalex", "arxiv"],
            "max_sources": 6,
            "publication_preference": "peer_reviewed_only",
            "evidence_preference": "abstract_only",
            "relevance_threshold": 60.0,
            "max_retries": 1,
        },
    )
    assert res_ok.status_code == 200
    run_data = res_ok.json()
    assert run_data["domain"] == "Condensed Matter Physics"
    assert run_data["max_sources"] == 6
    assert run_data["publication_preference"] == "peer_reviewed_only"
    assert run_data["evidence_preference"] == "abstract_only"
    assert run_data["relevance_threshold"] == 60.0
    assert run_data["max_retries"] == 1


def test_delete_research_run_cascades_and_updates_stats(workspace_project):
    """Verifies that deleting a research run cleans up all dependent records and updates workspace stats."""
    pid = workspace_project["id"]

    r1 = RunRepository.create(pid, "Inquiry to delete", domain="Computer Science")
    r2 = RunRepository.create(pid, "Inquiry to preserve", domain="Computer Science")

    # Add dependent records to r1
    s1 = SourceRepository.add(r1["id"], "Source for Run 1", doi="10.1111/r1")
    EvidenceRepository.add_passage(s1["id"], r1["id"], "Evidence passage 1")
    c1 = ClaimRepository.add(r1["id"], "Factual claim 1")
    ReportRepository.save(r1["id"], "Report 1", "# Report 1", "<p>Report 1</p>")

    stats_before = ProjectRepository.get_stats(pid)
    assert stats_before["runs_count"] == 2
    assert stats_before["sources_count"] >= 1
    assert stats_before["reports_count"] >= 1

    # Delete r1
    success = RunRepository.delete(r1["id"])
    assert success is True

    # r1 must be deleted
    assert RunRepository.get(r1["id"]) is None
    assert SourceRepository.list_by_run(r1["id"]) == []
    assert ClaimRepository.list_by_run(r1["id"]) == []
    assert ReportRepository.get_by_run(r1["id"]) is None

    # r2 must still exist
    assert RunRepository.get(r2["id"]) is not None

    # Stats must reflect deletion
    stats_after = ProjectRepository.get_stats(pid)
    assert stats_after["runs_count"] == 1


def test_api_delete_run_endpoint(workspace_project):
    """Tests the DELETE /api/runs/{run_id} endpoint."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    pid = workspace_project["id"]

    r = RunRepository.create(pid, "Inquiry for API deletion", domain="Computer Science")

    # 1. Successful deletion
    res = client.delete(f"/api/runs/{r['id']}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "deleted"
    assert data["run_id"] == r["id"]
    assert data["project_id"] == pid

    # 2. Deleting nonexistent run returns 404
    res_404 = client.delete(f"/api/runs/{r['id']}")
    assert res_404.status_code == 404


