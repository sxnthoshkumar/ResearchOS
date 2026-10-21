# System Architecture & Technical Design
## Autonomous AI Research Assistant with Multi-Agent Collaboration

### 1. Architectural Philosophy
The system implements an evidence-first, multi-agent collaborative framework that addresses common failure modes in single-agent research systems:
1. **Hallucination Prevention**: Claims are strictly decoupled from model intuition and must anchor to specific evidence passages with provenance.
2. **Deterministic Verification**: Independent auditing separates synthesis from verification, preventing the self-confirmation bias typical in monolithic LLM chains.
3. **Auditable Evidence Registry**: Extracted textual spans are indexed in an embedded SQLite database (leveraging FTS5 full-text indexing), ensuring every assertion is traceable to an authentic DOI or arXiv identifier.
4. **Resilient Offline Demonstration**: A deterministic Demonstration Provider mirrors realistic multi-agent behaviors and produces clearly labeled mock syntheses for academic demos without requiring external API keys.

---

### 2. Multi-Agent Pipeline Topology

```
+-----------------------------------------------------------------------------------+
|                                Research Dashboard                                 |
|         (Setup, Agent Monitor, Source Explorer, Claims, Final Report, Bench)       |
+-----------------------------------------------------------------------------------+
                                         |
                                         v  REST & Server-Sent Events (SSE)
+-----------------------------------------------------------------------------------+
|                               FastAPI Web Layer                                   |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                        Python Research Orchestrator                               |
|              Finite State Machine, Checkpoints, Bounded Retries                   |
+-----------------------------------------------------------------------------------+
          |                     |                  |               |
          v                     v                  v               v
   +--------------+      +--------------+   +--------------+ +--------------+
   | PlannerAgent | ---> | ResearchAgent| ->| AnalysisAgent| | FactChecker  |
   +--------------+      +--------------+   +--------------+ +--------------+
                                |                  |               |
                                v                  |               v
                         +---------------+         |        +--------------+
                         |Adapters/PyMuDF|         +------> | ReportWriter |
                         +---------------+                  +--------------+
                                |                                  |
                                v                                  v
+-----------------------------------------------------------------------------------+
|                     Embedded SQLite & FTS5 Evidence Registry                     |
|    (projects, runs, tasks, sources, passages, claims, verifications, reports)     |
+-----------------------------------------------------------------------------------+
```

---

### 3. Agent Specifications

| Agent | Core Responsibility | Input Schema | Output Schema |
|---|---|---|---|
| **Planner Agent** | Question validation, taxonomy decomposition, query formulation | `ResearchQuestionInput` | `ResearchPlan` (subquestions, targeted queries, outline) |
| **Research Agent** | OpenAlex/arXiv querying, deduplication, PDF ingestion | `ResearchPlan`, `AdapterConfig` | `SourceHarvest` (sources, passages, retrieval logs) |
| **Analysis Agent** | Passage synthesis, atomic claim extraction, correlation check | `SourceHarvest`, `Subquestions` | `AnalysisMatrix` (claims, direct findings, limitations) |
| **Fact-Checking Agent** | Evidence ground verification, verdict assignment | `ClaimList`, `PassageRegistry` | `VerificationAudit` (verdicts, rationale, citations) |
| **Report Writer Agent** | Synthesis assembly, quality gates, Markdown/HTML rendering | `VerifiedClaims`, `SourceList` | `ResearchReport` (sections, reference list, audits) |

---

### 4. Workflow Finite State Machine

The research orchestrator transitions through explicit states:

```
[ CREATED ]
     |
     v
[ PLANNING ] -----------> [ FAILED ] (invalid query / prompt error)
     |
     v
[ RESEARCHING ] --------> [ FAILED ] (unrecoverable network / source error)
     |
     v
[ ANALYZING ] ----------> [ FAILED ] (synthesis failure)
     |
     v
[ VERIFYING ] ----------> [ RETRYING ] (insufficient evidence / retry budget > 0)
     |                          |
     +<-------------------------+
     |
     v
[ GENERATING_REPORT ] --> [ EVALUATING ]
                                 |
                                 v
                            [ COMPLETED ]
```

- **Cancellation Support**: At any active state, an incoming cancellation signal cleanly flags the run as `CANCELLED`, preserving all existing partial sources and claims in SQLite.
- **Bounded Loops**: A maximum of 2 targeted search retries and 1 report revision are enforced.

---

### 5. Data Flow & Provenance Architecture

```
Academic Repositories (arXiv / OpenAlex)
                     |
                     v
             [ Source Adapter ]
                     |  (Deduplication by DOI/arXiv ID/normalized title)
                     v
           [ Document Extractor ]
                     |  (PyMuPDF PDF extraction or abstract cleaning)
                     v
       [ SQLite: `sources` & `evidence_passages` ]
                     |
                     v
              [ Analysis Agent ]
                     |  (Extracts atomic claims; links to passage IDs)
                     v
         [ SQLite: `claims` & `claim_evidence` ]
                     |
                     v
            [ Fact-Checking Agent ]
                     |  (Evaluates text alignment; computes support verdict)
                     v
       [ SQLite: `verification_results` ]
                     |
                     v
           [ Report Generation Agent ]
                     |  (Injects inline citations [1], builds bibliography)
                     v
              [ SQLite: `reports` ]
```

---

### 6. Persistence & SQLite Concurrency Model

1. **Embedded Zero-Config Storage**: Single file at `data/research_assistant.db`.
2. **Concurrency Configuration**:
   - Write-Ahead Logging (`PRAGMA journal_mode=WAL;`)
   - Extended busy timeout (`PRAGMA busy_timeout=10000;`)
   - Synchronous normal mode (`PRAGMA synchronous=NORMAL;`)
   - Foreign key integrity (`PRAGMA foreign_keys=ON;`)
3. **Full-Text Search Engine**:
   - Virtual table `evidence_fts` powered by SQLite `fts5` tokenizer.
   - Transparent fallback to parameterized `LIKE` operators if SQLite runtime lacks FTS5 compilation.
