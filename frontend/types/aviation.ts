// ═══════════════════════════════════════════════════════════════════
// Core event & run types (existing, enhanced)
// ═══════════════════════════════════════════════════════════════════

export type StageStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";
export type RunStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface Stage {
  stage_id: string;
  stage_name: string;
  stage_order: number;
  status: StageStatus;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  progress_pct: number;
  artifacts: string[];
  error_message?: string;
}

export interface RunMetadata {
  run_id: string;
  status: RunStatus;
  problem_description: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  current_stage?: string;
  stages_completed: number;
  total_stages: number;
  progress_pct: number;
  stages: Stage[];
  error_message?: string;
  error_stage?: string;
  event_count: number;
}

export interface WorkflowEvent {
  event_id: string;
  run_id: string;
  stream_id?: string;
  ts: string;
  sequence: number;
  level: "info" | "warn" | "error";
  kind: string;
  stage_id?: string;
  stage_name?: string;
  agent_name?: string;
  executor_name?: string;
  tool_name?: string;
  message: string;
  payload: Record<string, unknown>;
  actor?: TraceActor;
  trace_id?: string;
  span_id?: string;
  parent_span_id?: string;
  duration_ms?: number;
}

export interface TraceActor {
  kind: "orchestrator" | "agent" | "system" | string;
  id: string;
  name?: string;
}

export interface RunProgress {
  status: RunStatus;
  overallPct: number;
  agentsTotal: number;
  agentsActivated: number;
  agentsRunning: number;
  agentsDone: number;
  agentsErrored: number;
  currentStep: string;
  lastEventKind?: string;
  lastUpdateAt?: string;
  lastHeartbeatAt?: string;
  eventRatePerMin: number;
  isLive: boolean;
  isStale: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

// ═══════════════════════════════════════════════════════════════════
// Agent graph types (NEW — for orchestration canvas)
// ═══════════════════════════════════════════════════════════════════

export type AgentStatus =
  | "idle"
  | "activated"
  | "excluded"
  | "thinking"
  | "querying"
  | "done"
  | "error";

export interface AgentNode {
  id: string;
  name: string;
  shortName?: string;
  icon: string;
  color: string;
  status: AgentStatus;
  dataSources: string[];
  included: boolean;
  reason: string;
  category: "specialist" | "coordinator" | "placeholder";

  // Runtime data
  evidence: AgentEvidence[];
  toolCalls: AgentToolCall[];
  recommendation?: string;
  confidence?: number;
  activeQuery?: string; // current data source being queried

  // Trace enrichment (Phase 2)
  currentObjective?: string;
  activeQuerySummary?: string;
  lastEvidencePreview?: string;
  spanStartedAt?: string;
  traceCount?: number;
  lastTraceAt?: string;
  currentStep?: string;
  lastAction?: string;
  percentComplete?: number;
  startedAt?: string;
  endedAt?: string;
  durationMs?: number;
  completionReason?: string;
  executionCount?: number;
}

export interface AgentEvidence {
  id: string;
  sourceType: string;
  summary: string;
  resultCount: number;
  timestamp: string;
}

export interface AgentToolCall {
  id: string;
  toolName: string;
  dataSource: string;
  status: "running" | "done" | "error";
  startedAt?: string;
  endedAt?: string;
  latencyMs?: number;
  resultCount?: number;
  error?: string;
}

export interface AgentEdge {
  id: string;
  source: string;
  target: string;
  reason: string;
  animated: boolean;
  timestamp: string;
}

// ═══════════════════════════════════════════════════════════════════
// Agent metadata from API response
// ═══════════════════════════════════════════════════════════════════

export interface AgentInfo {
  id: string;
  name: string;
  icon: string;
  color: string;
  dataSources: string[];
  included: boolean;
  reason: string;
}

export interface SolveResponse {
  run_id: string;
  status: string;
  message: string;
  scenario: string;
  agents: AgentInfo[];
}

// ═══════════════════════════════════════════════════════════════════
// Data source activity types (NEW)
// ═══════════════════════════════════════════════════════════════════

export interface DataSourceActivity {
  id: string;
  name: string;
  type: string; // SQL, KQL, GRAPH, VECTOR_OPS, etc.
  provider: "Azure" | "Fabric" | "Unknown";
  platformLabel: string;
  queryCount: number;
  totalResults: number;
  avgLatencyMs: number;
  isActive: boolean;
  lastQueryTime?: string;
  lastQuerySummary?: string;
  lastAgentId?: string;
  // Sparkline data: last N query latencies
  sparkline: number[];
}

// ═══════════════════════════════════════════════════════════════════
// Recovery plan types (NEW)
// ═══════════════════════════════════════════════════════════════════

export interface RecoveryOption {
  optionId: string;
  description: string;
  rank: number;
  scores: {
    delay_reduction: number;
    crew_margin: number;
    safety_score: number;
    cost_impact: number;
    passenger_impact: number;
  };
  overallScore: number;
}

export interface RecoveryTimelineEntry {
  time: string;
  action: string;
  agent: string;
  details?: string;
  status: "pending" | "in_progress" | "completed";
}

export interface RecoveryPlan {
  selectedOptionId: string;
  summary: string;
  timeline: RecoveryTimelineEntry[];
  options: RecoveryOption[];
  criteria: string[];
}

// ═══════════════════════════════════════════════════════════════════
// Scenario types (NEW)
// ═══════════════════════════════════════════════════════════════════

export interface ScenarioCard {
  id: string;
  title: string;
  subtitle: string;
  icon: string;
  color: string;
  prompt: string;
}

// ═══════════════════════════════════════════════════════════════════
// Event kind constants (prevents string literal typos)
// ═══════════════════════════════════════════════════════════════════

export const EventKinds = {
  RUN_STARTED: "run_started",
  RUN_COMPLETED: "run_completed",
  RUN_FAILED: "run_failed",
  STAGE_STARTED: "stage_started",
  STAGE_COMPLETED: "stage_completed",
  STAGE_FAILED: "stage_failed",
  SPAN_STARTED: "span.started",
  SPAN_ENDED: "span.ended",
  AGENT_ACTIVATED: "agent.activated",
  AGENT_EXCLUDED: "agent.excluded",
  AGENT_EVIDENCE: "agent.evidence",
  AGENT_RECOMMENDATION: "agent.recommendation",
  AGENT_STREAMING: "agent.streaming",
  AGENT_OBJECTIVE: "agent.objective",
  AGENT_PROGRESS: "agent.progress",
  DATA_SOURCE_QUERY_START: "data_source.query_start",
  DATA_SOURCE_QUERY_COMPLETE: "data_source.query_complete",
  EXECUTOR_INVOKED: "executor.invoked",
  EXECUTOR_COMPLETED: "executor.completed",
  AGENT_COMPLETED: "agent.completed",
  AGENT_COMPLETED_LEGACY: "agent_completed",
  TOOL_CALLED: "tool.called",
  TOOL_COMPLETED: "tool.completed",
  TOOL_FAILED: "tool.failed",
  TOOL_CALLED_LEGACY: "tool_called",
  TOOL_COMPLETED_LEGACY: "tool_completed",
  TOOL_FAILED_LEGACY: "tool_failed",
  COORDINATOR_SCORING: "coordinator.scoring",
  COORDINATOR_PLAN: "coordinator.plan",
  RECOVERY_OPTION: "recovery.option",
  HANDOVER: "handover",
  ORCHESTRATOR_PLAN: "orchestrator.plan",
  ORCHESTRATOR_DECISION: "orchestrator.decision",
  HEARTBEAT: "heartbeat",
  PROGRESS_UPDATE: "progress_update",
  WORKFLOW_STATUS: "workflow.status",
} as const;

// ═══════════════════════════════════════════════════════════════════
// Payload helpers (safe extraction with type guards)
// ═══════════════════════════════════════════════════════════════════

export function payloadString(payload: Record<string, unknown>, key: string, fallback = ""): string {
  const val = payload[key];
  return typeof val === "string" ? val : fallback;
}

export function payloadNumber(payload: Record<string, unknown>, key: string, fallback = 0): number {
  const val = payload[key];
  return typeof val === "number" && !Number.isNaN(val) ? val : fallback;
}

export function payloadArray<T>(payload: Record<string, unknown>, key: string): T[] {
  const val = payload[key];
  return Array.isArray(val) ? (val as T[]) : [];
}

/** Safely parse a RecoveryTimelineEntry from unknown data. */
export function parseTimelineEntry(raw: unknown): RecoveryTimelineEntry | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  if (typeof obj.time !== "string" || typeof obj.action !== "string") return null;
  return {
    time: obj.time,
    action: obj.action,
    agent: typeof obj.agent === "string" ? obj.agent : "",
    details: typeof obj.details === "string" ? obj.details : undefined,
    status: (obj.status === "pending" || obj.status === "in_progress" || obj.status === "completed")
      ? obj.status
      : "pending",
  };
}

/** Safely parse RecoveryOption scores from unknown data. */
export function parseRecoveryScores(raw: unknown): RecoveryOption["scores"] {
  const fallback = { delay_reduction: 0, crew_margin: 0, safety_score: 0, cost_impact: 0, passenger_impact: 0 };
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return fallback;
  const obj = raw as Record<string, unknown>;
  return {
    delay_reduction: typeof obj.delay_reduction === "number" ? obj.delay_reduction : 0,
    crew_margin: typeof obj.crew_margin === "number" ? obj.crew_margin : 0,
    safety_score: typeof obj.safety_score === "number" ? obj.safety_score : 0,
    cost_impact: typeof obj.cost_impact === "number" ? obj.cost_impact : 0,
    passenger_impact: typeof obj.passenger_impact === "number" ? obj.passenger_impact : 0,
  };
}
