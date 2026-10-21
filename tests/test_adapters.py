"""
Unit tests for OpenAlex and arXiv scholarly source adapters using mocked HTTP responses.
"""

import pytest
from unittest.mock import AsyncMock, patch
import httpx

from app.research.openalex import OpenAlexAdapter
from app.research.arxiv import ArXivAdapter
from app.research.document_extractor import DocumentExtractor


SAMPLE_OPENALEX_JSON = {
    "results": [
        {
            "id": "https://openalex.org/W123456789",
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "publication_year": 2020,
            "doi": "https://doi.org/10.48550/arxiv.2005.11401",
            "type": "journal-article",
            "authorships": [
                {"author": {"display_name": "Patrick Lewis"}},
                {"author": {"display_name": "Ethan Perez"}},
            ],
            "abstract_inverted_index": {
                "Large": [0],
                "language": [1],
                "models": [2],
                "demonstrate": [3],
                "strong": [4],
                "reasoning": [5],
            },
            "open_access": {
                "is_oa": True,
                "oa_url": "https://arxiv.org/pdf/2005.11401.pdf",
            },
            "primary_location": {
                "pdf_url": "https://arxiv.org/pdf/2005.11401.pdf",
            },
        }
    ]
}

SAMPLE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2305.18290v1</id>
    <title>Direct Preference Optimization: Your Language Model is Secretly a Reward Model</title>
    <summary>We introduce Direct Preference Optimization (DPO), an algorithm for aligning language models.</summary>
    <published>2023-05-29T17:58:32Z</published>
    <author><name>Rafael Rafailov</name></author>
    <author><name>Archit Sharma</name></author>
    <link href="http://arxiv.org/abs/2305.18290v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2305.18290v1" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""


@pytest.mark.asyncio
async def test_openalex_adapter_mocked():
    adapter = OpenAlexAdapter()

    mock_resp = httpx.Response(
        status_code=200,
        json=SAMPLE_OPENALEX_JSON,
        request=httpx.Request("GET", "https://api.openalex.org/works"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        results = await adapter.search("RAG vs fine-tuning", limit=5)

        assert len(results) == 1
        item = results[0]
        assert item["title"] == "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
        assert item["publication_year"] == 2020
        assert item["doi"] == "10.48550/arxiv.2005.11401"
        assert "Patrick Lewis" in item["authors"]
        assert item["abstract"] == "Large language models demonstrate strong reasoning"
        assert item["access_status"] == "full_text_open"
        assert item["provider"] == "openalex"


@pytest.mark.asyncio
async def test_arxiv_adapter_mocked():
    adapter = ArXivAdapter()

    mock_resp = httpx.Response(
        status_code=200,
        text=SAMPLE_ARXIV_XML,
        request=httpx.Request("GET", "https://export.arxiv.org/api/query"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        results = await adapter.search("Direct Preference Optimization", limit=5)

        assert len(results) == 1
        item = results[0]
        assert item["title"] == "Direct Preference Optimization: Your Language Model is Secretly a Reward Model"
        assert item["publication_year"] == 2023
        assert item["arxiv_id"] == "2305.18290v1"
        assert "Rafael Rafailov" in item["authors"]
        assert "Direct Preference Optimization" in item["abstract"]
        assert item["provider"] == "arxiv"


def test_document_extractor_chunking():
    text = (
        "Paragraph 1 contains some detailed technical facts about distributed systems consensus. "
        "It explains that Raft is designed for understandability.\n\n"
        "Paragraph 2 discusses Paxos. Paxos uses two phases: prepare/promise and accept/accepted. "
        "It provides strong consistency guarantees under asynchronous networks.\n\n"
        "Paragraph 3 evaluates latency trade-offs between Raft and Multi-Paxos implementations."
    )
    chunks = DocumentExtractor.chunk_text(text, target_words=25)
    assert len(chunks) >= 1
    assert any("Raft" in c for c in chunks)


@pytest.mark.asyncio
async def test_openalex_rate_limit_and_timeout():
    adapter = OpenAlexAdapter()

    # 1. Test HTTP 429 rate limit handling
    mock_429 = httpx.Response(
        status_code=429,
        text="Rate limit exceeded",
        request=httpx.Request("GET", "https://api.openalex.org/works"),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_429
        results = await adapter.search("rate limit test")
        assert results == []

    # 2. Test TimeoutException handling
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ReadTimeout("Connection timed out")
        results = await adapter.search("timeout test")
        assert results == []


@pytest.mark.asyncio
async def test_arxiv_rate_limit_and_timeout():
    adapter = ArXivAdapter()

    # 1. Test HTTP 429 rate limit handling
    mock_429 = httpx.Response(
        status_code=429,
        text="Rate exceeded.",
        request=httpx.Request("GET", "https://export.arxiv.org/api/query"),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_429
        results = await adapter.search("rate exceeded test")
        assert results == []

    # 2. Test TimeoutException handling
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ReadTimeout("Connection timed out")
        results = await adapter.search("timeout test")
        assert results == []


@pytest.mark.asyncio
async def test_openalex_metadata_only_when_no_pdf_or_abstract():
    adapter = OpenAlexAdapter()
    meta_json = {
        "results": [
            {
                "id": "https://openalex.org/W99999",
                "title": "Title with No Abstract or PDF",
                "publication_year": 2021,
                "authorships": [{"author": {"display_name": "Dr. Minimal"}}],
                "doi": "https://doi.org/10.1000/minimal",
                "abstract_inverted_index": None,
                "open_access": {"is_oa": False, "oa_url": None},
                "primary_location": {"pdf_url": None},
            }
        ]
    }
    mock_resp = httpx.Response(
        status_code=200,
        json=meta_json,
        request=httpx.Request("GET", "https://api.openalex.org/works"),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        results = await adapter.search("minimal metadata")
        assert len(results) == 1
        assert results[0]["access_status"] == "metadata_only"
        assert results[0]["pdf_url"] is None
        assert results[0]["abstract"] is None


@pytest.mark.asyncio
async def test_evidence_retrieval_pipeline_provenance_and_access_status(monkeypatch, tmp_path):
    from app.database.db import DatabaseManager
    from app.database import db, repositories
    from app.research.evidence_retrieval import EvidenceRetrievalPipeline

    db_file = str(tmp_path / "test_pipeline.db")
    mgr = DatabaseManager(db_file)
    mgr.initialize_db()
    monkeypatch.setattr(db, "db_manager", mgr)
    monkeypatch.setattr(repositories, "db_manager", mgr)

    # Create dummy project and run
    proj = repositories.ProjectRepository.create("Test Proj", "Desc")
    run = repositories.RunRepository.create(proj["id"], "How does RAG compare to Fine-tuning?", provider_mode="live")

    pipeline = EvidenceRetrievalPipeline()

    # Mock OpenAlex returning 1 paper with abstract and 1 paper with metadata only
    mock_works = [
        {
            "title": "Empirical RAG Benchmark",
            "authors": ["Alice Smith"],
            "publication_year": 2024,
            "abstract": "This study comprehensively evaluates retrieval latency and parametric versus non-parametric knowledge retrieval.",
            "doi": "10.1000/rag.bench.2024",
            "arxiv_id": "2401.12345",
            "canonical_url": "https://doi.org/10.1000/rag.bench.2024",
            "pdf_url": None,
            "provider": "openalex",
            "access_status": "abstract_only",
            "doc_type": "article",
            "raw_metadata": {},
        },
        {
            "title": "Minimal Meta Work",
            "authors": ["Bob Jones"],
            "publication_year": 2022,
            "abstract": None,
            "doi": "10.1000/minimal.2022",
            "arxiv_id": None,
            "canonical_url": "https://doi.org/10.1000/minimal.2022",
            "pdf_url": None,
            "provider": "openalex",
            "access_status": "metadata_only",
            "doc_type": "article",
            "raw_metadata": {},
        },
    ]

    with patch.object(pipeline.openalex, "search", new_callable=AsyncMock) as mock_oa, \
         patch.object(pipeline.arxiv, "search", new_callable=AsyncMock) as mock_ar:
        mock_oa.return_value = mock_works
        mock_ar.return_value = []

        sources = await pipeline.execute_search(
            run_id=run["id"],
            query="empirical rag benchmark",
            subquestion_id="sq-1",
            is_demo=False,
        )

        assert len(sources) == 2

        # Check source 1 (with abstract)
        s1 = next(s for s in sources if s["title"] == "Empirical RAG Benchmark")
        assert s1["access_status"] == "abstract_only"
        assert s1["inspected_full_text"] == 0
        assert s1["provider"] == "openalex"

        # Check source 2 (metadata only)
        s2 = next(s for s in sources if s["title"] == "Minimal Meta Work")
        assert s2["access_status"] == "metadata_only"
        assert s2["inspected_full_text"] == 0

        # Verify SQLite passages and foreign key provenance
        passages = repositories.EvidenceRepository.list_by_run(run["id"])
        # Only s1 has an abstract, so passages must belong only to s1
        assert len(passages) >= 1
        for p in passages:
            assert p["source_id"] == s1["id"]
            assert p["extraction_method"] == "abstract"

        # Verify demo search creates distinctly labeled DEMO records
        demo_sources = await pipeline.execute_search(
            run_id=run["id"],
            query="demo query",
            subquestion_id="sq-2",
            is_demo=True,
        )
        assert len(demo_sources) >= 1
        for ds in demo_sources:
            assert ds["provider"] == "demo"
            assert "[DEMO BENCHMARK]" in ds["title"]

