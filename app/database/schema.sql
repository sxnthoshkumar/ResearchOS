-- Autonomous AI Research Assistant Schema

PRAGMA foreign_keys = ON;

-- 1. Research Projects
CREATE TABLE IF NOT EXISTS research_projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Research Runs
CREATE TABLE IF NOT EXISTS research_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL, -- CREATED, PLANNING, RESEARCHING, ANALYZING, VERIFYING, RETRYING, GENERATING_REPORT, EVALUATING, COMPLETED, FAILED, CANCELLED
    provider_mode TEXT NOT NULL, -- demo, openai, generic
    model_name TEXT,
    search_providers TEXT NOT NULL, -- openalex,arxiv or comma-separated
    max_sources INTEGER NOT NULL DEFAULT 10,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    error_message TEXT,
    start_time TEXT,
    completed_time TEXT,
    duration_seconds REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES research_projects(id) ON DELETE CASCADE
);

-- 3. Agent Tasks
CREATE TABLE IF NOT EXISTS agent_tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_name TEXT NOT NULL, -- planner, researcher, analyst, fact_checker, report_writer
    task_name TEXT NOT NULL,
    status TEXT NOT NULL, -- PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    input_data TEXT, -- JSON serialized
    output_data TEXT, -- JSON serialized
    error_message TEXT,
    start_time TEXT,
    end_time TEXT,
    duration_seconds REAL,
    retry_attempt INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

-- 4. Sources
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    title TEXT NOT NULL,
    authors TEXT, -- JSON or comma-separated
    publication_year INTEGER,
    abstract TEXT,
    doi TEXT,
    arxiv_id TEXT,
    canonical_url TEXT,
    provider TEXT NOT NULL, -- openalex, arxiv, demo
    access_status TEXT NOT NULL, -- full_text_open, abstract_only, restricted
    doc_type TEXT, -- journal, preprint, conference
    inspected_full_text INTEGER NOT NULL DEFAULT 0, -- 1 if full text PDF was parsed, 0 if abstract only
    raw_metadata TEXT, -- JSON
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

-- 5. Evidence Passages
CREATE TABLE IF NOT EXISTS evidence_passages (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    passage_text TEXT NOT NULL,
    page_number INTEGER,
    extraction_method TEXT NOT NULL, -- pymupdf, abstract, demo_synthesis
    subquestion_id TEXT,
    relevance_score REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

-- 6. Claims
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    subquestion_id TEXT,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL DEFAULT 'factual', -- factual, comparative, limitation
    section_target TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

-- 7. Claim Evidence Mapping (M:N)
CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (claim_id, evidence_id),
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_id) REFERENCES evidence_passages(id) ON DELETE CASCADE
);

-- 8. Verification Results
CREATE TABLE IF NOT EXISTS verification_results (
    id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    verdict TEXT NOT NULL, -- SUPPORTED, PARTIALLY_SUPPORTED, CONTRADICTED, INSUFFICIENT_EVIDENCE, INVALID_CITATION
    rationale TEXT NOT NULL,
    support_score REAL NOT NULL DEFAULT 0.0,
    contradiction_found INTEGER NOT NULL DEFAULT 0,
    contradicting_evidence TEXT,
    supporting_excerpts TEXT, -- JSON array
    verification_method TEXT,
    confidence REAL DEFAULT 0.0,
    is_direct_quote INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

-- 9. Final Reports
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    markdown_content TEXT NOT NULL,
    html_content TEXT NOT NULL,
    quality_summary TEXT, -- JSON string with gate evaluations
    citation_count INTEGER DEFAULT 0,
    verified_claim_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

-- 10. Benchmark Questions
CREATE TABLE IF NOT EXISTS benchmark_questions (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    question TEXT NOT NULL,
    required_subtopics TEXT NOT NULL, -- JSON array
    expected_evidence_density INTEGER DEFAULT 5,
    min_sources INTEGER DEFAULT 3,
    criteria TEXT, -- JSON checklist
    created_at TEXT NOT NULL
);

-- 11. Benchmark Runs
CREATE TABLE IF NOT EXISTS benchmark_runs (
    id TEXT PRIMARY KEY,
    benchmark_question_id TEXT NOT NULL,
    system_variant TEXT NOT NULL, -- 'five_agent_collaborative' or 'single_agent_baseline'
    run_id TEXT,
    status TEXT NOT NULL, -- PENDING, COMPLETED, FAILED
    start_time TEXT,
    completed_time TEXT,
    duration_seconds REAL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (benchmark_question_id) REFERENCES benchmark_questions(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE SET NULL
);

-- 12. Benchmark Results
CREATE TABLE IF NOT EXISTS benchmark_results (
    id TEXT PRIMARY KEY,
    benchmark_run_id TEXT NOT NULL,
    retrieval_relevance REAL,
    research_coverage REAL,
    claim_support_rate REAL,
    citation_correctness REAL,
    task_completion INTEGER,
    runtime_seconds REAL,
    estimated_cost_usd REAL,
    detailed_metrics TEXT, -- JSON
    created_at TEXT NOT NULL,
    FOREIGN KEY (benchmark_run_id) REFERENCES benchmark_runs(id) ON DELETE CASCADE
);

-- 13. App Settings & Migrations
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 14. Source Relevance Evaluations
CREATE TABLE IF NOT EXISTS source_relevance_evaluations (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    research_question TEXT NOT NULL,
    relevance_score REAL NOT NULL,
    direct_relevance REAL NOT NULL,
    methodology_relevance REAL NOT NULL,
    findings_relevance REAL NOT NULL,
    domain_relevance REAL NOT NULL,
    direct_explanation TEXT,
    methodology_explanation TEXT,
    findings_explanation TEXT,
    domain_explanation TEXT,
    decision TEXT NOT NULL, -- INCLUDE, REVIEW, EXCLUDE
    is_metadata_only INTEGER NOT NULL DEFAULT 0,
    positive_signals TEXT, -- JSON array
    missing_information TEXT, -- JSON array
    excerpts TEXT, -- JSON array of {text, provenance}
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

-- 15. Source Publication Classifications
CREATE TABLE IF NOT EXISTS source_publication_classifications (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    venue_name TEXT,
    document_type TEXT,
    publication_status TEXT,
    peer_review_status TEXT NOT NULL, -- PEER_REVIEWED_JOURNAL, PEER_REVIEWED_CONFERENCE, PREPRINT, WORKSHOP_OR_OTHER, TECHNICAL_REPORT, UNKNOWN
    classification_evidence TEXT,
    metadata_source TEXT,
    last_verified_date TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

-- Indexes for optimal lookup and foreign key joins
CREATE INDEX IF NOT EXISTS idx_runs_project ON research_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_run ON agent_tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_sources_run ON sources(run_id);
CREATE INDEX IF NOT EXISTS idx_passages_source ON evidence_passages(source_id);
CREATE INDEX IF NOT EXISTS idx_passages_run ON evidence_passages(run_id);
CREATE INDEX IF NOT EXISTS idx_claims_run ON claims(run_id);
CREATE INDEX IF NOT EXISTS idx_verification_claim ON verification_results(claim_id);
CREATE INDEX IF NOT EXISTS idx_reports_run ON reports(run_id);
CREATE INDEX IF NOT EXISTS idx_bench_results_run ON benchmark_results(benchmark_run_id);
CREATE INDEX IF NOT EXISTS idx_relevance_source ON source_relevance_evaluations(source_id);
CREATE INDEX IF NOT EXISTS idx_relevance_run ON source_relevance_evaluations(run_id);
CREATE INDEX IF NOT EXISTS idx_pub_class_source ON source_publication_classifications(source_id);
CREATE INDEX IF NOT EXISTS idx_pub_class_run ON source_publication_classifications(run_id);
