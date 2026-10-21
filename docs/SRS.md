# Software Requirements Specification (SRS)
## Autonomous AI Research Assistant with Multi-Agent Collaboration

### 1. Introduction
#### 1.1 Purpose
This document provides a formal specification of the software requirements for the **Autonomous AI Research Assistant with Multi-Agent Collaboration**. The system automates scholarly literature retrieval, evidence extraction, factual synthesis, claim-level fact-checking, and comprehensive report generation using a five-agent collaborative architecture.

#### 1.2 Scope
The application executes end-to-end research workflows on complex scholarly questions. It integrates directly with scholarly open-access repositories (OpenAlex, arXiv), performs PDF/abstract text extraction, maintains an auditable SQLite evidence registry, and supports both deterministic demonstration execution and real OpenAI-compatible API inference without external vector database or server dependencies.

#### 1.3 Intended Audience
University evaluators, academic researchers, AI system engineers, and peer reviewers assessing multi-agent systems, information retrieval pipelines, and automated fact-checking methodologies.

---

### 2. Overall Description
#### 2.1 System Architecture Overview
The system follows a modular, pipeline-orchestrated multi-agent architecture:
1. **Research Dashboard (UI)**: Built with vanilla HTML5, CSS3, and modern JavaScript, served directly by FastAPI. Provides real-time SSE progress updates, source exploration, verification audits, and report generation controls.
2. **FastAPI Application**: Exposes REST and SSE endpoints for project orchestration, live status streaming, evidence exploration, and report exports.
3. **Research Orchestrator**: Enforces an explicit workflow finite state machine (`CREATED`, `PLANNING`, `RESEARCHING`, `ANALYZING`, `VERIFYING`, `RETRYING`, `GENERATING_REPORT`, `EVALUATING`, `COMPLETED`, `FAILED`, `CANCELLED`).
4. **Five Specialized Agents**:
   - **Planner Agent**: Decomposes the research question into subquestions, search queries, and evidence criteria.
   - **Research Agent**: Queries OpenAlex & arXiv, normalizes metadata, deduplicates papers, downloads abstracts/PDFs via PyMuPDF, and populates the evidence registry.
   - **Analysis Agent**: Synthesizes passages into atomic factual claims linked to source citations.
   - **Fact-Checking Agent**: Verifies claim grounds against extracted evidence, assigning verdicts (`SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, `CONFLICTING`, `NOT_CHECKABLE`).
   - **Report Generation Agent**: Formulates a structured, citation-grounded research report in Markdown/HTML with quality gate validation.
5. **SQLite Persistence Engine**: Embedded relational storage (`data/research_assistant.db`) managing projects, runs, agent tasks, sources, passages, claims, verification records, reports, and benchmark evaluations with full-text search (FTS5) capabilities.

#### 2.2 Operational Environment
- **Runtime**: Python 3.10+ on Windows, Linux, or macOS.
- **Database**: Local SQLite 3 with FTS5 and WAL mode support.
- **Dependencies**: Minimal (FastAPI, Uvicorn, Pydantic, HTTPX, PyMuPDF, Jinja2, Pytest).
- **Network**: Internet access required only for live scholarly APIs (arXiv, OpenAlex) or hosted LLM endpoints; fully functional offline via the built-in deterministic Demonstration Provider.

---

### 3. Functional Requirements

#### FR-1: Project and Run Management
- **FR-1.1**: The system shall create, view, list, and delete research projects stored in SQLite.
- **FR-1.2**: Deletion of a project shall cascade to all runs, tasks, sources, evidence, claims, verification records, and reports.
- **FR-1.3**: The system shall maintain state machine transitions with UTC timestamps, execution metrics, and error logs.
- **FR-1.4**: Runs can be cancelled safely, terminating downstream agent execution without corrupting existing records.

#### FR-2: Five-Agent Responsibilities
- **FR-2.1 (Planner)**: Validate research queries, formulate at least 3 subquestions, construct targeted search strings, and establish section outlines.
- **FR-2.2 (Researcher)**: Query OpenAlex and arXiv APIs, deduplicate based on DOI/arXiv ID/title, ingest abstracts or full PDF text using PyMuPDF, and link passages to subquestions.
- **FR-2.3 (Analyst)**: Extract atomic factual claims from retrieved passages, preserve explicit claim-to-evidence mappings, and distinguish direct findings from interpretations.
- **FR-2.4 (Fact-Checker)**: Independently evaluate claim assertions against stored passage text, detecting hallucinations, citation errors, and contradictory statements.
- **FR-2.5 (Report Writer)**: Synthesize verified claims into academic sections (Executive Summary, Methodology, Findings, Comparative Analysis, Limitations, Gaps, References) with inline clickable citations.

#### FR-3: Quality Gates & Retries
- **FR-3.1**: Prior to finalizing a report, the orchestrator shall evaluate Evidence Sufficiency and Report Quality gates.
- **FR-3.2**: Targeted retries are bounded to a maximum of 2 additional search iterations and 1 report revision per run.
- **FR-3.3**: Disputed or uncheckable claims shall be flagged and explicitly documented in the Limitations section.

#### FR-4: User Interface & Presentation
- **FR-4.1**: Six dedicated views: Setup, Agent Monitor, Source Explorer, Verification Results, Final Report, and Evaluation History.
- **FR-4.2**: Real-time agent status streaming via Server-Sent Events (SSE) with resilient polling fallback.
- **FR-4.3**: Canonical report export to Markdown (.md) and standalone HTML (.html).
- **FR-4.4**: Explicit badge indicator distinguishing Demo Mode from live AI model execution.

---

### 4. Non-Functional Requirements

#### NFR-1: Reliability & Correctness
- Real research metadata shall never be forged or fabricated.
- Untrusted scholarly texts and PDF extractions must be sanitized against prompt injection and cross-site scripting (XSS).
- Secret API credentials must never be committed, logged, or sent to client browsers.

#### NFR-2: Performance & Scalability
- SQLite connection pooling with WAL mode, parameterized statements, and configured busy timeouts (`busy_timeout=10000ms`).
- Bounded network timeouts (25s default) and graceful fallback if external academic APIs are unreachable.

#### NFR-3: Testability & Reproducibility
- 100% of core unit and integration tests must run without requiring active network connectivity or paid API keys.
- Comprehensive evaluation benchmark across 20 diverse research questions evaluating precision, citation validity, and claim verification rates.
