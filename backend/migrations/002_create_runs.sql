-- Migration 002: Create runs table

CREATE TABLE IF NOT EXISTS aviation_solver.runs (
    run_id VARCHAR(50) PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    problem_description TEXT DEFAULT '',
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    current_stage VARCHAR(50),
    stages_completed INTEGER DEFAULT 0,
    progress_pct REAL DEFAULT 0,
    error_message TEXT,
    error_stage VARCHAR(50),
    event_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_av_runs_status ON aviation_solver.runs(status);
CREATE INDEX IF NOT EXISTS idx_av_runs_created ON aviation_solver.runs(created_at DESC);
