# Testing Strategy & Verification Guide
## Autonomous AI Research Assistant with Multi-Agent Collaboration

### 1. Overview
The testing suite guarantees that all system components—agents, research source adapters, persistence layers, state machines, quality gates, and API routes—operate reliably without requiring live paid AI APIs or external database services.

---

### 2. Test Architecture
Tests are executed using `pytest` and `pytest-asyncio` organized into the following suites:

| Test Suite | Purpose | Target Modules |
|---|---|---|
| `test_database.py` | Schema creation, WAL mode, migrations, cascade deletes, concurrent access | `app.database` |
| `test_adapters.py` | OpenAlex and arXiv HTTP mocking, parsing, deduplication, rate limiting | `app.research` |
| `test_agents.py` | Unit tests for Planner, Research, Analysis, Fact-Checking, Report Writer | `app.agents` |
| `test_orchestrator.py` | State machine transitions, bounded retries, task recording, cancellation | `app.orchestration` |
| `test_verification_gates.py`| Claim grounding, citation resolution, gate enforcement, limitation audits | `app.agents.fact_checker` |
| `test_api.py` | FastAPI route endpoints, SSE event streams, export endpoints | `app.api` |
| `test_e2e_workflow.py` | End-to-end multi-agent execution in demonstration mode | Entire pipeline |
| `test_security.py` | Prompt injection defenses, HTML sanitization, secret redaction | Security utilities |

---

### 3. Execution Commands

#### Run Full Test Suite
```bash
# Windows
.venv\Scripts\pytest.exe -v

# Linux / macOS
.venv/bin/pytest -v
```

#### Run Specific Test Modules
```bash
.venv\Scripts\pytest.exe tests/test_database.py -v
.venv\Scripts\pytest.exe tests/test_agents.py -v
.venv\Scripts\pytest.exe tests/test_orchestrator.py -v
```

---

### 4. Continuous Integration Safeguards
- Zero live paid API calls during testing (enforced via mock fixtures).
- Parameterized database testing in dedicated in-memory or temporary SQLite files.
- Deterministic random seeds and provider responses for reproducible assertions.
