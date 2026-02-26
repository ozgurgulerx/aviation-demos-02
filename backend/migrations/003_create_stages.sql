-- Migration 003: Create stages table

CREATE TABLE IF NOT EXISTS aviation_solver.stages (
    run_id VARCHAR(50) REFERENCES aviation_solver.runs(run_id) ON DELETE CASCADE,
    stage_id VARCHAR(50),
    stage_name VARCHAR(100),
    stage_order INTEGER,
    status VARCHAR(20) DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    progress_pct REAL DEFAULT 0,
    error_message TEXT,
    PRIMARY KEY (run_id, stage_id)
);
