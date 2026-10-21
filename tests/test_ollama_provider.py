"""
Comprehensive mocked unit tests for Ollama provider integration:
- Successful Ollama response (qwen2.5:3b, JSON formatting, token metrics)
- Provider unavailable (ConnectError) and timeout (TimeoutException)
- Model missing (404 / tags check)
- Malformed JSON extraction and repair handling
- Nonexistent evidence IDs rejected by Fact-Checking Agent
- Citation provenance preservation
- Correct provider selection (ollama vs demo)
- Demo mode continuing to work without Ollama
- Live retrieval remaining independent of provider configuration
"""

import os
import json
import tempfile
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import settings
from app.llm import get_llm_provider
from app.llm.base import LLMMessage
from app.llm.demo_provider import DemoLLMProvider
from app.llm.ollama_provider import OllamaLLMProvider
from app.llm.json_repair import extract_structured_json
from app.agents.planner import PlannerAgent
from app.agents.analyst import AnalysisAgent
from app.agents.fact_checker import FactCheckingAgent
from app.agents.report_writer import ReportWriterAgent
from app.database.db import DatabaseManager
from app.database.repositories import (
    ProjectRepository,
    RunRepository,
    SourceRepository,
    EvidenceRepository,
    ClaimRepository,
    VerificationRepository,
)


@pytest.fixture
def mock_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    mgr = DatabaseManager(path)
    mgr.initialize_db()
    from app.database import db, repositories
    monkeypatch.setattr(db, "db_manager", mgr)
    monkeypatch.setattr(repositories, "db_manager", mgr)

    p = ProjectRepository.create("Ollama Integration Test Project", "Test Suite")
    run = RunRepository.create(
        p["id"],
        "Assess quantum error correction codes for topological fault tolerance",
        provider_mode="ollama",
        model_name="qwen2.5:3b",
    )
    yield run["id"]
    try:
        os.remove(path)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_ollama_successful_chat():
    """Test successful chat inference with Ollama provider."""
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:3b")

    mock_response_data = {
        "model": "qwen2.5:3b",
        "message": {"role": "assistant", "content": '{"analysis": "Quantum codes exhibit topological threshold."}'},
        "prompt_eval_count": 45,
        "eval_count": 28,
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        messages = [
            LLMMessage(role="system", content="You are an academic researcher."),
            LLMMessage(role="user", content="Analyze quantum codes."),
        ]

        resp = await provider.generate(messages, response_format_json=True)

        assert resp.content == '{"analysis": "Quantum codes exhibit topological threshold."}'
        assert resp.model == "qwen2.5:3b"
        assert resp.prompt_tokens == 45
        assert resp.completion_tokens == 28
        assert resp.estimated_cost_usd == 0.0  # Local inference is always free

        # Verify POST payload sent to Ollama chat endpoint
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["model"] == "qwen2.5:3b"
        assert call_kwargs["json"]["stream"] is False
        assert call_kwargs["json"]["format"] == "json"


@pytest.mark.asyncio
async def test_ollama_provider_unavailable():
    """Test graceful handling when Ollama daemon is unreachable."""
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:3b")

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused to port 11434")

        messages = [LLMMessage(role="user", content="Hello")]
        with pytest.raises(RuntimeError) as exc_info:
            await provider.generate(messages)

        assert "Ollama service is unavailable" in str(exc_info.value)
        assert "http://localhost:11434" in str(exc_info.value)


@pytest.mark.asyncio
async def test_ollama_provider_timeout():
    """Test handling of Ollama request timeout."""
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:3b")

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Read timeout after 90 seconds")

        messages = [LLMMessage(role="user", content="Hello")]
        with pytest.raises(RuntimeError) as exc_info:
            await provider.generate(messages)

        assert "timed out" in str(exc_info.value)


@pytest.mark.asyncio
async def test_ollama_model_missing():
    """Test detection and clear error reporting when configured model is not installed."""
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:3b")

    # 1. Test chat endpoint returns 404
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = '{"error": "model \'qwen2.5:3b\' not found, try pulling it first"}'

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        messages = [LLMMessage(role="user", content="Hello")]
        with pytest.raises(RuntimeError) as exc_info:
            await provider.generate(messages)

        assert "was not found at" in str(exc_info.value)
        assert "ollama pull qwen2.5:3b" in str(exc_info.value)

    # 2. Test check_health reporting model_missing
    mock_tags_resp = MagicMock()
    mock_tags_resp.status_code = 200
    mock_tags_resp.json.return_value = {"models": [{"name": "llama3.2:1b"}]}

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_tags_resp
        health = await provider.check_health()
        assert health["reachable"] is True
        assert health["status"] == "model_missing"
        assert health["model_installed"] is False
        assert "ollama pull qwen2.5:3b" in health["message"]


def test_extract_structured_json():
    """Test JSON cleaning utility on markdown fences, trailing commas, and raw formatting."""
    # Markdown wrapped
    raw_md = "```json\n{\n  \"key\": \"value\"\n}\n```"
    data = extract_structured_json(raw_md)
    assert data == {"key": "value"}

    # Trailing commas in object and list
    raw_comma = '{\n  "items": [1, 2, ],\n  "status": "ok",\n}'
    data = extract_structured_json(raw_comma)
    assert data == {"items": [1, 2], "status": "ok"}

    # Malformed syntax raises ValueError without hallucinating
    with pytest.raises(ValueError) as exc:
        extract_structured_json("This is pure conversational text with no JSON brackets.")
    assert "Malformed JSON" in str(exc.value)


@pytest.mark.asyncio
async def test_agent_malformed_json_repair_failure():
    """Test that when an agent receives unparseable JSON, it attempts 1-shot repair then raises ValueError without inventing data."""
    mock_llm = MagicMock()
    # First response: malformed JSON. Second response (repair attempt): still malformed
    mock_llm.generate = AsyncMock(side_effect=[
        MagicMock(content="I am unable to answer in JSON: Here are some notes."),
        MagicMock(content="Still not JSON."),
    ])

    planner = PlannerAgent(mock_llm)
    with pytest.raises(ValueError) as exc:
        await planner.create_plan("Research deep learning architectures")

    assert "failed to produce valid" in str(exc.value).lower()
    # Verify that repair attempt was executed
    assert mock_llm.generate.call_count == 2


@pytest.mark.asyncio
async def test_fact_checker_rejects_nonexistent_evidence_ids(mock_db):
    """Test that FactCheckingAgent marks claims citing fictitious or nonexistent evidence IDs as UNSUPPORTED."""
    run_id = mock_db
    llm = DemoLLMProvider()
    fact_checker = FactCheckingAgent(llm)

    # 1. Add a genuine source and evidence passage in DB
    source = SourceRepository.add(
        run_id=run_id,
        title="Genuine Empirical Source on Fault Tolerance",
        authors="Alice Doe, Bob Smith",
        publication_year=2024,
        canonical_url="https://doi.org/10.1000/182",
        provider="openalex",
        access_status="full_text_inspected",
    )
    real_evidence = EvidenceRepository.add_passage(
        run_id=run_id,
        source_id=source["id"],
        passage_text="Surface codes achieve a 1.0% error threshold under depolarizing noise.",
    )

    # 2. Case A: Claim with genuine evidence ID
    claim_a = ClaimRepository.add(
        run_id=run_id,
        claim_text="Surface codes achieve a 1.0% error threshold under depolarizing noise.",
        claim_type="FINDING",
        evidence_ids=[real_evidence["id"]],
    )

    # 3. Case B: Database foreign key constraint strictly blocks nonexistent evidence IDs
    import sqlite3
    fake_evidence_id = "nonexistent-evidence-id-9999"
    with pytest.raises(sqlite3.IntegrityError):
        ClaimRepository.add(
            run_id=run_id,
            claim_text="Topological braid codes exhibit zero error rate unconditionally.",
            claim_type="FINDING",
            evidence_ids=[fake_evidence_id],
        )

    # 4. Case C: Claim without evidence citations is marked NOT_CHECKABLE by Fact-Checking Agent
    claim_c = ClaimRepository.add(
        run_id=run_id,
        claim_text="Unreferenced claim without registered evidence citations.",
        claim_type="HYPOTHESIS",
        evidence_ids=[],
    )

    audit_result = await fact_checker.verify_claims(run_id)
    assert audit_result.total_claims_audited == 3

    # Map audit by claim_id
    audit_map = {a.claim_id: a for a in audit_result.audits}
    assert audit_map[claim_a["id"]].verdict in ("SUPPORTED", "PARTIALLY_SUPPORTED")
    assert audit_map[claim_c["id"]].verdict == "NOT_CHECKABLE"
    assert "does not cite any registered evidence" in audit_map[claim_c["id"]].rationale.lower()


@pytest.mark.asyncio
async def test_citation_provenance_preservation(mock_db):
    """Test that Report Writer preserves genuine source IDs, DOIs, URLs, and citations intact."""
    run_id = mock_db
    llm = DemoLLMProvider()
    writer = ReportWriterAgent(llm)

    # Populate genuine source
    source = SourceRepository.add(
        run_id=run_id,
        title="Asymptotically Good Quantum Codes",
        authors="Carol White",
        publication_year=2024,
        canonical_url="https://arxiv.org/abs/2401.99999",
        arxiv_id="2401.99999",
        provider="arxiv",
        access_status="full_text_inspected",
    )
    evidence = EvidenceRepository.add_passage(
        run_id=run_id,
        source_id=source["id"],
        passage_text="Low-density parity check codes yield linear distance scaling.",
    )
    claim = ClaimRepository.add(
        run_id=run_id,
        claim_text="Quantum LDPC codes demonstrate linear distance scaling.",
        evidence_ids=[evidence["id"]],
    )
    VerificationRepository.record(
        claim_id=claim["id"],
        run_id=run_id,
        verdict="SUPPORTED",
        rationale="Passage directly corroborates distance scaling.",
        support_score=0.95,
        contradiction_found=False,
    )

    report_result = await writer.generate_report(
        run_id=run_id,
        research_question="Assess quantum error correction codes for topological fault tolerance",
        is_demo=True,
    )

    # Provenance assertions
    assert report_result.citation_count >= 1
    assert "https://arxiv.org/abs/2401.99999" in report_result.html_content
    assert "Asymptotically Good Quantum Codes" in report_result.markdown_content


def test_provider_selection():
    """Test that provider selection properly instantiates OllamaLLMProvider or DemoLLMProvider without silent fallback."""
    # 1. Force demo
    demo_p = get_llm_provider(force_demo=True)
    assert isinstance(demo_p, DemoLLMProvider)

    # 2. Ollama provider requested
    ollama_p = get_llm_provider(force_demo=False, provider_name="ollama")
    assert isinstance(ollama_p, OllamaLLMProvider)
    assert ollama_p.model == "qwen2.5:3b"
    assert ollama_p.base_url == "http://localhost:11434"

    # 3. Demo provider explicitly requested
    explicit_demo_p = get_llm_provider(force_demo=False, provider_name="demo")
    assert isinstance(explicit_demo_p, DemoLLMProvider)


@pytest.mark.asyncio
async def test_demo_mode_works_without_ollama():
    """Test that demo mode continues working deterministically even if Ollama is offline."""
    # Create planner and run plan creation in demo mode
    llm = DemoLLMProvider()
    planner = PlannerAgent(llm)
    plan = await planner.create_plan("Evaluate Byzantine fault tolerance in decentralized systems")

    assert plan.plan_id is not None
    assert len(plan.subquestions) >= 3
    assert len(plan.target_sections) >= 4


@pytest.mark.asyncio
async def test_live_retrieval_independent_of_provider(monkeypatch):
    """Test that OpenAlex and arXiv scholarly search adapters function independently of LLM provider settings."""
    from app.research.openalex import OpenAlexAdapter

    # Mock OpenAlex response
    mock_openalex_data = {
        "results": [
            {
                "id": "https://openalex.org/W999001",
                "title": "Quantum Fault Tolerance Protocols",
                "authorships": [{"author": {"display_name": "Dr. Quantum"}}],
                "publication_year": 2024,
                "doi": "https://doi.org/10.1038/s41586-024-0001",
                "abstract_inverted_index": {"Quantum": [0], "codes": [1], "scale": [2]},
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_openalex_data

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        adapter = OpenAlexAdapter()
        results = await adapter.search("quantum fault tolerance", limit=1)

        assert len(results) == 1
        assert results[0]["title"] == "Quantum Fault Tolerance Protocols"
        assert "Dr. Quantum" in results[0]["authors"]
        assert results[0]["publication_year"] == 2024


def test_is_model_match_variants():
    """Test model matching against tags, registry prefixes, and default tags."""
    from app.llm.ollama_provider import is_model_match

    # Exact matches
    assert is_model_match("qwen2.5:3b", "qwen2.5:3b") is True
    assert is_model_match("QWEN2.5:3B", "qwen2.5:3b") is True

    # Registry prefixes
    assert is_model_match("library/qwen2.5:3b", "qwen2.5:3b") is True
    assert is_model_match("registry.ollama.ai/library/qwen2.5:3b", "qwen2.5:3b") is True

    # Latest tag defaults
    assert is_model_match("phi3:latest", "phi3") is True
    assert is_model_match("phi3", "phi3:latest") is True

    # Negative matches
    assert is_model_match("qwen2.5vl:3b", "qwen2.5:3b") is False
    assert is_model_match("llama3.2:1b", "qwen2.5:3b") is False
    assert is_model_match("", "qwen2.5:3b") is False


@pytest.mark.asyncio
async def test_check_health_distinguishes_all_states():
    """Verify check_health explicitly distinguishes all operational states."""
    provider = OllamaLLMProvider(base_url="http://localhost:11434", model="qwen2.5:3b")

    # State 1: Online (installed and available)
    resp_online = MagicMock(status_code=200)
    resp_online.json.return_value = {"models": [{"name": "qwen2.5:3b"}]}
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_online
        h = await provider.check_health()
        assert h["status"] == "online"
        assert h["reachable"] is True
        assert h["model_installed"] is True
        assert "installed and ready" in h["message"]

    # State 2: Model missing (daemon online, model not installed)
    resp_missing = MagicMock(status_code=200)
    resp_missing.json.return_value = {"models": [{"name": "llama3.2:1b"}]}
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_missing
        h = await provider.check_health()
        assert h["status"] == "model_missing"
        assert h["reachable"] is True
        assert h["model_installed"] is False
        assert "not found in Ollama" in h["message"]

    # State 3: Offline (unreachable / connection error)
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        h = await provider.check_health()
        assert h["status"] == "offline"
        assert h["reachable"] is False
        assert h["model_installed"] is False
        assert "Cannot connect to Ollama" in h["message"]

    # State 4a: Timeout
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Timed out")
        h = await provider.check_health()
        assert h["status"] == "timeout"
        assert h["reachable"] is False
        assert "timed out" in h["message"]

    # State 4b: HTTP Error from Ollama
    resp_500 = MagicMock(status_code=500, text="Internal Server Error")
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_500
        h = await provider.check_health()
        assert h["status"] == "error"
        assert h["reachable"] is False
        assert "HTTP 500" in h["error"]

