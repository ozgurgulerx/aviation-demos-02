"use client";

import { create } from "zustand";
import type {
  WorkflowEvent,
  RunMetadata,
  Stage,
  AgentNode,
  AgentEdge,
  AgentInfo,
  DataSourceActivity,
  RecoveryPlan,
  RecoveryOption,
  RunProgress,
} from "@/types/aviation";
import {
  EventKinds,
  payloadString,
  payloadNumber,
  payloadArray,
  parseTimelineEntry,
  parseRecoveryScores,
} from "@/types/aviation";

// ═══════════════════════════════════════════════════════════════════
// Data source registry
// ═══════════════════════════════════════════════════════════════════

const DATA_SOURCE_DEFAULTS: Record<
  string,
  {
    name: string;
    type: string;
    provider: DataSourceActivity["provider"];
    platformLabel: string;
  }
> = {
  SQL: { name: "Azure PostgreSQL", type: "SQL", provider: "Azure", platformLabel: "Azure Data" },
  KQL: { name: "Fabric Eventhouse", type: "KQL", provider: "Fabric", platformLabel: "Microsoft Fabric" },
  GRAPH: { name: "Fabric Graph", type: "GRAPH", provider: "Fabric", platformLabel: "Microsoft Fabric" },
  VECTOR_OPS: { name: "Azure AI Search (Ops)", type: "VECTOR_OPS", provider: "Azure", platformLabel: "Azure AI" },
  VECTOR_REG: { name: "Azure AI Search (Regs)", type: "VECTOR_REG", provider: "Azure", platformLabel: "Azure AI" },
  VECTOR_AIRPORT: { name: "Azure AI Search (Airport)", type: "VECTOR_AIRPORT", provider: "Azure", platformLabel: "Azure AI" },
  NOSQL: { name: "Azure Cosmos DB", type: "NOSQL", provider: "Azure", platformLabel: "Azure Data" },
  FABRIC_SQL: { name: "Fabric SQL Endpoint", type: "FABRIC_SQL", provider: "Fabric", platformLabel: "Microsoft Fabric" },
};

function createDefaultDataSources(): Record<string, DataSourceActivity> {
  const sources: Record<string, DataSourceActivity> = {};
  for (const [key, val] of Object.entries(DATA_SOURCE_DEFAULTS)) {
    sources[key] = {
      id: key,
      name: val.name,
      type: val.type,
      provider: val.provider,
      platformLabel: val.platformLabel,
      queryCount: 0,
      totalResults: 0,
      avgLatencyMs: 0,
      isActive: false,
      sparkline: [],
    };
  }
  return sources;
}

function incrementAgentTrace(agent: AgentNode, ts: string): AgentNode {
  return {
    ...agent,
    traceCount: (agent.traceCount ?? 0) + 1,
    lastTraceAt: ts,
  };
}

function createDefaultRunProgress(): RunProgress {
  return {
    status: "pending",
    overallPct: 0,
    agentsTotal: 0,
    agentsActivated: 0,
    agentsRunning: 0,
    agentsDone: 0,
    agentsErrored: 0,
    currentStep: "idle",
    eventRatePerMin: 0,
    isLive: false,
    isStale: false,
  };
}

function isMeaningfulEvent(kind: string): boolean {
  return kind !== EventKinds.HEARTBEAT;
}

const MAX_STORED_EVENTS = 1500;

// ═══════════════════════════════════════════════════════════════════
// Store interface
// ═══════════════════════════════════════════════════════════════════

interface AviationStore {
  // Existing: Run state
  currentRunId: string | null;
  currentRun: RunMetadata | null;
  events: WorkflowEvent[];
  isConnected: boolean;
  lastEventId: string | null;
  runProgress: RunProgress;
  activeAgentIds: string[];
  completedAgentIds: string[];
  failedAgentIds: string[];
  lastMeaningfulEventAt: string | null;
  lastHeartbeatAt: string | null;
  eventRatePerMin: number;
  noUpdateWarning: boolean;

  // NEW: Scenario
  scenario: string | null;

  // NEW: Agent graph state
  agents: Record<string, AgentNode>;
  agentEdges: AgentEdge[];
  selectedAgentId: string | null;

  // NEW: Data source activity
  dataSources: Record<string, DataSourceActivity>;

  // NEW: Recovery output
  recoveryPlan: RecoveryPlan | null;
  recoveryOptions: RecoveryOption[];

  // NEW: UI layout state
  sidebarCollapsed: boolean;
  bottomDrawerTab: "activity" | "timeline" | "plan" | "sources";
  bottomDrawerOpen: boolean;

  // Actions
  setCurrentRunId: (runId: string | null) => void;
  setCurrentRun: (run: RunMetadata | null) => void;
  updateRunFromEvent: (event: WorkflowEvent) => void;
  addEvent: (event: WorkflowEvent) => void;
  clearEvents: () => void;
  setConnected: (connected: boolean) => void;
  noteHeartbeat: (ts?: string) => void;
  evaluateStaleness: (nowMs?: number) => void;

  // NEW: Agent actions
  initializeAgents: (agentInfos: AgentInfo[], scenario: string) => void;
  setSelectedAgent: (agentId: string | null) => void;
  processAgentEvent: (event: WorkflowEvent) => void;

  // NEW: UI actions
  setSidebarCollapsed: (collapsed: boolean) => void;
  setBottomDrawerTab: (tab: "activity" | "timeline" | "plan" | "sources") => void;
  setBottomDrawerOpen: (open: boolean) => void;

  // Computed
  getStageByName: (name: string) => Stage | undefined;
  getIncludedAgents: () => AgentNode[];
  getExcludedAgents: () => AgentNode[];
}

// ═══════════════════════════════════════════════════════════════════
// Store implementation
// ═══════════════════════════════════════════════════════════════════

export const useAviationStore = create<AviationStore>((set, get) => ({
  // Existing state
  currentRunId: null,
  currentRun: null,
  events: [],
  isConnected: false,
  lastEventId: null,
  runProgress: createDefaultRunProgress(),
  activeAgentIds: [],
  completedAgentIds: [],
  failedAgentIds: [],
  lastMeaningfulEventAt: null,
  lastHeartbeatAt: null,
  eventRatePerMin: 0,
  noUpdateWarning: false,

  // New state
  scenario: null,
  agents: {},
  agentEdges: [],
  selectedAgentId: null,
  dataSources: createDefaultDataSources(),
  recoveryPlan: null,
  recoveryOptions: [],
  sidebarCollapsed: false,
  bottomDrawerTab: "timeline",
  bottomDrawerOpen: true,

  // Existing actions
  setCurrentRunId: (runId) =>
    set((state) => ({
      currentRunId: runId,
      runProgress: runId
        ? { ...state.runProgress, status: "running", isLive: true, currentStep: "run_started" }
        : createDefaultRunProgress(),
    })),
  setCurrentRun: (run) => set({ currentRun: run }),

  updateRunFromEvent: (event) => {
    const state = get();
    if (!state.currentRun) return;
    const run = { ...state.currentRun };

    switch (event.kind) {
      case EventKinds.STAGE_STARTED:
        if (event.stage_id) {
          run.current_stage = event.stage_id;
          const stage = run.stages.find((s) => s.stage_id === event.stage_id);
          if (stage) {
            stage.status = "running";
            stage.started_at = event.ts;
          }
        }
        break;
      case EventKinds.STAGE_COMPLETED:
        if (event.stage_id) {
          const stage = run.stages.find((s) => s.stage_id === event.stage_id);
          if (stage) {
            stage.status = "succeeded";
            stage.completed_at = event.ts;
            stage.duration_ms = event.duration_ms;
          }
          run.stages_completed = run.stages.filter(
            (s) => s.status === "succeeded" || s.status === "skipped"
          ).length;
          run.progress_pct = (run.stages_completed / run.total_stages) * 100;
        }
        break;
      case EventKinds.STAGE_FAILED:
        if (event.stage_id) {
          const stage = run.stages.find((s) => s.stage_id === event.stage_id);
          if (stage) {
            stage.status = "failed";
            stage.error_message = event.message;
          }
        }
        break;
      case EventKinds.RUN_COMPLETED:
        run.status = "completed";
        run.completed_at = event.ts;
        break;
      case EventKinds.RUN_FAILED:
        run.status = "failed";
        run.error_message = event.message;
        break;
    }

    run.event_count = state.events.length + 1;
    set({ currentRun: run });
  },

  addEvent: (event) => {
    const effectiveTs = event.ts || new Date().toISOString();
    set((state) => {
      const recentEvents = [...state.events, event].slice(-MAX_STORED_EVENTS);
      const cutoffMs = Date.now() - 60_000;
      const eventRatePerMin = recentEvents.filter((e) => {
        const t = Date.parse(e.ts);
        return Number.isFinite(t) && t >= cutoffMs && e.kind !== EventKinds.HEARTBEAT;
      }).length;

      const payload = event.payload || {};
      const runPct = payloadNumber(payload, "runProgressPct", state.runProgress.overallPct);
      const nextProgress: RunProgress = {
        ...state.runProgress,
        overallPct: Math.max(state.runProgress.overallPct, runPct),
        status:
          event.kind === EventKinds.RUN_COMPLETED
            ? "completed"
            : event.kind === EventKinds.RUN_FAILED
            ? "failed"
            : event.kind === EventKinds.RUN_STARTED
            ? "running"
            : state.runProgress.status,
        currentStep: payloadString(payload, "currentStep", state.runProgress.currentStep),
        lastEventKind: event.kind,
        lastUpdateAt: effectiveTs,
        eventRatePerMin,
        isLive: state.isConnected,
      };

      return {
        events: recentEvents,
        lastEventId: event.stream_id || event.event_id,
        lastMeaningfulEventAt: isMeaningfulEvent(event.kind) ? effectiveTs : state.lastMeaningfulEventAt,
        eventRatePerMin,
        runProgress: nextProgress,
      };
    });
    get().updateRunFromEvent(event);
    get().processAgentEvent(event);
  },

  clearEvents: () =>
    set({
      events: [],
      currentRunId: null,
      currentRun: null,
      lastEventId: null,
      runProgress: createDefaultRunProgress(),
      activeAgentIds: [],
      completedAgentIds: [],
      failedAgentIds: [],
      lastMeaningfulEventAt: null,
      lastHeartbeatAt: null,
      eventRatePerMin: 0,
      noUpdateWarning: false,
      scenario: null,
      agents: {},
      agentEdges: [],
      selectedAgentId: null,
      dataSources: createDefaultDataSources(),
      recoveryPlan: null,
      recoveryOptions: [],
    }),

  setConnected: (connected) =>
    set((state) => ({
      isConnected: connected,
      noUpdateWarning: connected ? state.noUpdateWarning : false,
      runProgress: { ...state.runProgress, isLive: connected, isStale: connected ? state.runProgress.isStale : false },
    })),

  noteHeartbeat: (ts) =>
    set((state) => {
      const heartbeatTs = ts || new Date().toISOString();
      return {
        lastHeartbeatAt: heartbeatTs,
        runProgress: { ...state.runProgress, lastHeartbeatAt: heartbeatTs },
      };
    }),

  evaluateStaleness: (nowMs) =>
    set((state) => {
      const now = nowMs ?? Date.now();
      const lastMeaningfulMs = state.lastMeaningfulEventAt ? Date.parse(state.lastMeaningfulEventAt) : 0;
      const stale = state.isConnected && lastMeaningfulMs > 0 && now - lastMeaningfulMs > 20_000;
      return {
        noUpdateWarning: stale,
        runProgress: { ...state.runProgress, isStale: stale },
      };
    }),

  // ── NEW: Agent initialization from solve response ──────────
  initializeAgents: (agentInfos, scenario) => {
    const agents: Record<string, AgentNode> = {};
    const includedCount = agentInfos.filter((a) => a.included).length;
    for (const info of agentInfos) {
      agents[info.id] = {
        id: info.id,
        name: info.name,
        icon: info.icon,
        color: info.color,
        status: info.included ? "idle" : "excluded",
        dataSources: info.dataSources,
        included: info.included,
        reason: info.reason,
        category: info.id.includes("coordinator") ? "coordinator" : "specialist",
        evidence: [],
        toolCalls: [],
        traceCount: 0,
        percentComplete: 0,
        executionCount: 0,
      };
    }
    set((state) => ({
      agents,
      scenario,
      agentEdges: [],
      activeAgentIds: [],
      completedAgentIds: [],
      failedAgentIds: [],
      runProgress: {
        ...state.runProgress,
        status: "running",
        agentsTotal: includedCount,
        agentsActivated: 0,
        agentsRunning: 0,
        agentsDone: 0,
        agentsErrored: 0,
        overallPct: 0,
        currentStep: "agents_initialized",
      },
    }));
  },

  setSelectedAgent: (agentId) => set({ selectedAgentId: agentId }),

  // ── NEW: Event routing — dispatches SSE events to correct state ──
  processAgentEvent: (event) => {
    const payload = event.payload || {};
    const agentId =
      payloadString(payload, "agentId") ||
      payloadString(payload, "executor_id") ||
      event.agent_name ||
      "";
    const agentName =
      payloadString(payload, "agentName") ||
      payloadString(payload, "agent_name") ||
      event.agent_name ||
      agentId;
    const reportedRunPct = payloadNumber(payload, "runProgressPct", -1);
    const reportedCurrentStep = payloadString(payload, "currentStep");

    switch (event.kind) {
      case EventKinds.AGENT_ACTIVATED: {
        if (!agentId) break;
        set((state) => ({
          agents: {
            ...state.agents,
              [agentId]: {
              ...incrementAgentTrace(state.agents[agentId] || {
                id: agentId,
                name: agentName || agentId,
                icon: payloadString(payload, "icon"),
                color: payloadString(payload, "color", "#6366f1"),
                dataSources: payloadArray<string>(payload, "dataSources"),
                included: true,
                reason: payloadString(payload, "reason"),
                category: "specialist" as const,
                evidence: [],
                toolCalls: [],
                status: "idle" as const,
                traceCount: 0,
                percentComplete: 0,
                executionCount: 0,
              }, event.ts),
              status: "activated" as const,
              startedAt: state.agents[agentId]?.startedAt || event.ts,
              lastAction: "activated",
            },
          },
          activeAgentIds: Array.from(new Set([...state.activeAgentIds, agentId])),
          runProgress: {
            ...state.runProgress,
            agentsActivated: Math.max(state.runProgress.agentsActivated, state.activeAgentIds.length + 1),
            agentsRunning: Array.from(new Set([...state.activeAgentIds, agentId])).length,
            currentStep: reportedCurrentStep || `activated:${agentId}`,
            overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
            lastEventKind: event.kind,
            lastUpdateAt: event.ts,
          },
        }));
        break;
      }

      case EventKinds.AGENT_EXCLUDED: {
        if (!agentId || !get().agents[agentId]) break;
        set((state) => ({
          agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                status: "excluded" as const,
                lastAction: "excluded",
              },
            },
          activeAgentIds: state.activeAgentIds.filter((id) => id !== agentId),
          runProgress: {
            ...state.runProgress,
            agentsRunning: state.activeAgentIds.filter((id) => id !== agentId).length,
            currentStep: reportedCurrentStep || `excluded:${agentId}`,
            overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
            lastEventKind: event.kind,
            lastUpdateAt: event.ts,
          },
        }));
        break;
      }

      case EventKinds.SPAN_STARTED: {
        if (agentId && get().agents[agentId]) {
          const objective = payloadString(payload, "objective") || payloadString(payload, "spanName") || event.message;
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                status: "thinking" as const,
                currentObjective: objective,
                spanStartedAt: event.ts,
                startedAt: state.agents[agentId].startedAt || event.ts,
                currentStep: payloadString(payload, "currentStep", "analyzing"),
                lastAction: "thinking",
                percentComplete: Math.max(state.agents[agentId].percentComplete ?? 0, payloadNumber(payload, "percentComplete", 10)),
              },
            },
            activeAgentIds: Array.from(new Set([...state.activeAgentIds, agentId])),
            runProgress: {
              ...state.runProgress,
              agentsRunning: Array.from(new Set([...state.activeAgentIds, agentId])).length,
              currentStep: reportedCurrentStep || `thinking:${agentId}`,
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.AGENT_OBJECTIVE: {
        if (agentId && get().agents[agentId]) {
          const objective = payloadString(payload, "objective", event.message);
          const currentStep = payloadString(payload, "currentStep", "objective_set");
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                currentObjective: objective,
                currentStep,
                lastAction: "objective_updated",
                percentComplete: Math.max(state.agents[agentId].percentComplete ?? 0, payloadNumber(payload, "percentComplete", 5)),
              },
            },
            runProgress: {
              ...state.runProgress,
              currentStep: reportedCurrentStep || currentStep,
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.AGENT_PROGRESS:
      case EventKinds.AGENT_STREAMING: {
        if (agentId && get().agents[agentId]) {
          const percentComplete = payloadNumber(payload, "percentComplete", Math.min((get().agents[agentId].percentComplete ?? 0) + 6, 92));
          const currentStep = payloadString(payload, "currentStep", "streaming");
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                status: "thinking" as const,
                currentStep,
                lastAction: "streaming",
                percentComplete,
              },
            },
            activeAgentIds: Array.from(new Set([...state.activeAgentIds, agentId])),
            runProgress: {
              ...state.runProgress,
              agentsRunning: Array.from(new Set([...state.activeAgentIds, agentId])).length,
              currentStep: reportedCurrentStep || currentStep,
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.EXECUTOR_INVOKED: {
        if (agentId && get().agents[agentId]) {
          const currentStep = payloadString(payload, "currentStep", "executor_invoked");
          const executionCount = payloadNumber(
            payload,
            "executionCount",
            (get().agents[agentId].executionCount ?? 0) + 1
          );
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                status: "thinking" as const,
                currentStep,
                lastAction: "executor_invoked",
                startedAt: state.agents[agentId].startedAt || event.ts,
                executionCount,
              },
            },
            activeAgentIds: Array.from(new Set([...state.activeAgentIds, agentId])),
            runProgress: {
              ...state.runProgress,
              agentsRunning: Array.from(new Set([...state.activeAgentIds, agentId])).length,
              currentStep: reportedCurrentStep || currentStep,
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.EXECUTOR_COMPLETED: {
        if (agentId && get().agents[agentId]) {
          const status = payloadString(payload, "status", "completed");
          const isFailure = status === "failed";
          const executionCount = payloadNumber(
            payload,
            "executionCount",
            get().agents[agentId].executionCount ?? 1
          );
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                status: isFailure ? ("error" as const) : ("done" as const),
                endedAt: event.ts,
                lastAction: "executor_completed",
                percentComplete: Math.max(state.agents[agentId].percentComplete ?? 0, 95),
                executionCount,
              },
            },
            activeAgentIds: state.activeAgentIds.filter((id) => id !== agentId),
            runProgress: {
              ...state.runProgress,
              agentsRunning: state.activeAgentIds.filter((id) => id !== agentId).length,
              currentStep: reportedCurrentStep || `executor_completed:${agentId}`,
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.DATA_SOURCE_QUERY_START: {
        const sourceType = payloadString(payload, "sourceType");
        const querySummary = payloadString(payload, "querySummary") || payloadString(payload, "query") || `Querying ${sourceType}...`;
        const sourceProvider = payloadString(payload, "sourceProvider");
        if (agentId && get().agents[agentId]) {
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                status: "querying" as const,
                activeQuery: sourceType,
                activeQuerySummary: querySummary,
                currentStep: payloadString(payload, "currentStep", `query:${sourceType}`),
                lastAction: "query_started",
                percentComplete: Math.max(state.agents[agentId].percentComplete ?? 0, payloadNumber(payload, "percentComplete", 20)),
              },
            },
            dataSources: {
              ...state.dataSources,
              ...(sourceType && state.dataSources[sourceType]
                ? {
                    [sourceType]: {
                      ...state.dataSources[sourceType],
                      isActive: true,
                      lastAgentId: agentId,
                      lastQuerySummary: querySummary,
                      provider:
                        sourceProvider === "Fabric" || sourceProvider === "Azure"
                          ? sourceProvider
                          : state.dataSources[sourceType].provider,
                    },
                  }
                : {}),
            },
            runProgress: {
              ...state.runProgress,
              currentStep: reportedCurrentStep || `query:${sourceType}`,
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.DATA_SOURCE_QUERY_COMPLETE: {
        const sourceType = payloadString(payload, "sourceType");
        const resultCount = payloadNumber(payload, "resultCount");
        const latencyMs = payloadNumber(payload, "latencyMs");
        const sourceProvider = payloadString(payload, "sourceProvider");
        const querySummary = payloadString(payload, "querySummary", `${sourceType} query`);

        set((state) => {
          const ds = state.dataSources[sourceType];
          const newDs = ds
            ? {
                ...ds,
                queryCount: ds.queryCount + 1,
                totalResults: ds.totalResults + resultCount,
                avgLatencyMs: Math.round(
                  (ds.avgLatencyMs * ds.queryCount + latencyMs) / (ds.queryCount + 1)
                ),
                isActive: false,
                lastQueryTime: event.ts,
                lastQuerySummary: querySummary,
                lastAgentId: agentId || ds.lastAgentId,
                provider: sourceProvider === "Fabric" || sourceProvider === "Azure"
                  ? sourceProvider
                  : ds.provider,
                sparkline: [...ds.sparkline.slice(-19), latencyMs],
              }
            : undefined;

          const agent = agentId ? state.agents[agentId] : undefined;
          const evidenceSummary = querySummary;
          const newAgent = agent
            ? {
                ...incrementAgentTrace(agent, event.ts),
                status: "thinking" as const,
                activeQuery: undefined,
                activeQuerySummary: undefined,
                currentStep: payloadString(payload, "currentStep", `query_complete:${sourceType}`),
                lastAction: "query_completed",
                percentComplete: Math.max(agent.percentComplete ?? 0, payloadNumber(payload, "percentComplete", 55)),
                lastEvidencePreview: `${resultCount} results from ${sourceType} (${latencyMs}ms)`,
                evidence: [
                  ...agent.evidence,
                  {
                    id: `ev-${Date.now()}`,
                    sourceType,
                    summary: evidenceSummary,
                    resultCount,
                    timestamp: event.ts,
                  },
                ],
              }
            : undefined;

          return {
            dataSources: newDs
              ? { ...state.dataSources, [sourceType]: newDs }
              : state.dataSources,
            agents: newAgent
              ? { ...state.agents, [agentId]: newAgent }
              : state.agents,
            runProgress: {
              ...state.runProgress,
              currentStep: reportedCurrentStep || `query_complete:${sourceType}`,
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          };
        });
        break;
      }

      case EventKinds.TOOL_CALLED:
      case EventKinds.TOOL_CALLED_LEGACY: {
        const toolName = payloadString(payload, "toolName", event.tool_name || "tool");
        if (agentId && get().agents[agentId]) {
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                toolCalls: [
                  ...state.agents[agentId].toolCalls,
                  {
                    id: payloadString(payload, "toolId", `tool-${Date.now()}`),
                    toolName,
                    dataSource: payloadString(payload, "sourceType", payloadString(payload, "dataSource", "unknown")),
                    status: "running",
                    startedAt: event.ts,
                  },
                ],
                currentStep: payloadString(payload, "currentStep", `tool:${toolName}`),
                lastAction: "tool_called",
              },
            },
          }));
        }
        break;
      }

      case EventKinds.TOOL_COMPLETED:
      case EventKinds.TOOL_COMPLETED_LEGACY:
      case EventKinds.TOOL_FAILED:
      case EventKinds.TOOL_FAILED_LEGACY: {
        const toolName = payloadString(payload, "toolName", event.tool_name || "tool");
        const toolId = payloadString(payload, "toolId");
        const isFailure = event.kind === EventKinds.TOOL_FAILED || event.kind === EventKinds.TOOL_FAILED_LEGACY;
        if (agentId && get().agents[agentId]) {
          set((state) => {
            const existing = state.agents[agentId].toolCalls;
            const targetIndex = toolId
              ? existing.findIndex((tc) => tc.id === toolId)
              : (() => {
                  for (let i = existing.length - 1; i >= 0; i -= 1) {
                    if (existing[i].toolName === toolName && existing[i].status === "running") return i;
                  }
                  return -1;
                })();
            const updatedCalls = [...existing];
            if (targetIndex >= 0) {
              updatedCalls[targetIndex] = {
                ...updatedCalls[targetIndex],
                status: isFailure ? "error" : "done",
                endedAt: event.ts,
                latencyMs: payloadNumber(payload, "latencyMs", updatedCalls[targetIndex].latencyMs),
                resultCount: payloadNumber(payload, "resultCount", updatedCalls[targetIndex].resultCount),
                error: isFailure ? payloadString(payload, "error", event.message) : undefined,
              };
            }
            return {
              agents: {
                ...state.agents,
                [agentId]: {
                  ...incrementAgentTrace(state.agents[agentId], event.ts),
                  toolCalls: updatedCalls,
                  lastAction: isFailure ? "tool_failed" : "tool_completed",
                },
              },
            };
          });
        }
        break;
      }

      case EventKinds.AGENT_EVIDENCE: {
        if (agentId && get().agents[agentId]) {
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                currentStep: payloadString(payload, "currentStep", "evidence_collected"),
                lastAction: "evidence_collected",
                evidence: [
                  ...state.agents[agentId].evidence,
                  {
                    id: `ev-${Date.now()}`,
                    sourceType: payloadString(payload, "sourceType", "unknown"),
                    summary: payloadString(payload, "summary", event.message),
                    resultCount: payloadNumber(payload, "resultCount"),
                    timestamp: event.ts,
                  },
                ],
              },
            },
            runProgress: {
              ...state.runProgress,
              currentStep: reportedCurrentStep || "evidence_collected",
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.AGENT_RECOMMENDATION: {
        if (agentId && get().agents[agentId]) {
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                recommendation: payloadString(payload, "recommendation"),
                confidence: payloadNumber(payload, "confidence"),
                currentStep: payloadString(payload, "currentStep", "recommendation_ready"),
                lastAction: "recommendation_ready",
                percentComplete: Math.max(state.agents[agentId].percentComplete ?? 0, 85),
              },
            },
            runProgress: {
              ...state.runProgress,
              currentStep: reportedCurrentStep || "recommendation_ready",
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.SPAN_ENDED: {
        if (agentId && get().agents[agentId]) {
          const success = payload.success !== false;
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                status: success ? ("done" as const) : ("error" as const),
                currentObjective: undefined,
                activeQuerySummary: undefined,
                spanStartedAt: undefined,
                endedAt: event.ts,
                durationMs: payloadNumber(payload, "durationMs", state.agents[agentId].durationMs),
                completionReason: payloadString(payload, "completionReason", success ? "completed" : "failed"),
                lastAction: success ? "completed" : "failed",
                percentComplete: success ? 100 : state.agents[agentId].percentComplete,
              },
            },
            activeAgentIds: state.activeAgentIds.filter((id) => id !== agentId),
            completedAgentIds: success
              ? Array.from(new Set([...state.completedAgentIds, agentId]))
              : state.completedAgentIds,
            failedAgentIds: !success
              ? Array.from(new Set([...state.failedAgentIds, agentId]))
              : state.failedAgentIds,
            runProgress: {
              ...state.runProgress,
              agentsRunning: state.activeAgentIds.filter((id) => id !== agentId).length,
              agentsDone: success
                ? Array.from(new Set([...state.completedAgentIds, agentId])).length
                : state.completedAgentIds.length,
              agentsErrored: !success
                ? Array.from(new Set([...state.failedAgentIds, agentId])).length
                : state.failedAgentIds.length,
              currentStep: reportedCurrentStep || (success ? `completed:${agentId}` : `failed:${agentId}`),
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.AGENT_COMPLETED:
      case EventKinds.AGENT_COMPLETED_LEGACY: {
        if (agentId && get().agents[agentId]) {
          const status = payloadString(payload, "status", "completed");
          const isSuccess = status !== "failed";
          const executionCount = payloadNumber(
            payload,
            "executionCount",
            get().agents[agentId].executionCount ?? 1
          );
          set((state) => ({
            agents: {
              ...state.agents,
              [agentId]: {
                ...incrementAgentTrace(state.agents[agentId], event.ts),
                status: isSuccess ? "done" : "error",
                recommendation:
                  payloadString(payload, "summary") || state.agents[agentId].recommendation,
                completionReason: payloadString(payload, "completionReason", status),
                startedAt: payloadString(payload, "startedAt", state.agents[agentId].startedAt),
                endedAt: payloadString(payload, "endedAt", event.ts),
                durationMs: payloadNumber(payload, "durationMs", state.agents[agentId].durationMs),
                percentComplete: 100,
                lastAction: isSuccess ? "agent_completed" : "agent_failed",
                executionCount,
              },
            },
            activeAgentIds: state.activeAgentIds.filter((id) => id !== agentId),
            completedAgentIds: isSuccess
              ? Array.from(new Set([...state.completedAgentIds, agentId]))
              : state.completedAgentIds,
            failedAgentIds: !isSuccess
              ? Array.from(new Set([...state.failedAgentIds, agentId]))
              : state.failedAgentIds,
            runProgress: {
              ...state.runProgress,
              agentsRunning: state.activeAgentIds.filter((id) => id !== agentId).length,
              agentsDone: isSuccess
                ? Array.from(new Set([...state.completedAgentIds, agentId])).length
                : state.completedAgentIds.length,
              agentsErrored: !isSuccess
                ? Array.from(new Set([...state.failedAgentIds, agentId])).length
                : state.failedAgentIds.length,
              currentStep: reportedCurrentStep || `agent_completed:${agentId}`,
              overallPct: reportedRunPct >= 0 ? reportedRunPct : Math.max(state.runProgress.overallPct, 90),
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.HANDOVER: {
        const fromAgent = payloadString(payload, "fromAgent");
        const toAgent = payloadString(payload, "toAgent");
        if (fromAgent && toAgent) {
          set((state) => ({
            agents: {
              ...state.agents,
              ...(state.agents[fromAgent]
                ? { [fromAgent]: incrementAgentTrace(state.agents[fromAgent], event.ts) }
                : {}),
              ...(state.agents[toAgent]
                ? { [toAgent]: incrementAgentTrace(state.agents[toAgent], event.ts) }
                : {}),
            },
            agentEdges: [
              ...state.agentEdges,
              {
                id: `edge-${fromAgent}-${toAgent}-${Date.now()}`,
                source: fromAgent,
                target: toAgent,
                reason: payloadString(payload, "reason"),
                animated: true,
                timestamp: event.ts,
              },
            ],
            runProgress: {
              ...state.runProgress,
              currentStep: reportedCurrentStep || `handover:${fromAgent}->${toAgent}`,
              overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
              lastEventKind: event.kind,
              lastUpdateAt: event.ts,
            },
          }));
        }
        break;
      }

      case EventKinds.COORDINATOR_SCORING: {
        const options = payloadArray<RecoveryOption>(payload, "options");
        const criteria = payloadArray<string>(payload, "criteria");
        set({ recoveryOptions: options });
        if (get().recoveryPlan) {
          set((state) => ({
            recoveryPlan: state.recoveryPlan
              ? { ...state.recoveryPlan, options, criteria }
              : null,
          }));
        }
        // Auto-open plan tab
        set({ bottomDrawerTab: "plan", bottomDrawerOpen: true });
        break;
      }

      case EventKinds.COORDINATOR_PLAN: {
        const currentOptions = get().recoveryOptions;
        const rawTimeline = Array.isArray(payload.timeline) ? payload.timeline : [];
        const timeline = rawTimeline
          .map((entry: unknown) => parseTimelineEntry(entry))
          .filter((e): e is NonNullable<typeof e> => e !== null);
        set({
          recoveryPlan: {
            selectedOptionId: payloadString(payload, "selectedOptionId"),
            summary: payloadString(payload, "summary"),
            timeline,
            options: currentOptions.length > 0 ? currentOptions : payloadArray<RecoveryOption>(payload, "options"),
            criteria: ["delay_reduction", "crew_margin", "safety_score", "cost_impact", "passenger_impact"],
          },
          bottomDrawerTab: "plan",
          bottomDrawerOpen: true,
        });
        break;
      }

      case EventKinds.RECOVERY_OPTION: {
        const scores = parseRecoveryScores(payload.scores);
        const option: RecoveryOption = {
          optionId: payloadString(payload, "optionId"),
          description: payloadString(payload, "description"),
          rank: payloadNumber(payload, "rank"),
          scores,
          overallScore: 0,
        };
        option.overallScore =
          scores.delay_reduction * 0.25 + scores.crew_margin * 0.15 +
          scores.safety_score * 0.25 + scores.cost_impact * 0.15 + scores.passenger_impact * 0.20;
        set((state) => ({
          recoveryOptions: [...state.recoveryOptions, option],
        }));
        break;
      }

      case EventKinds.ORCHESTRATOR_PLAN:
      case EventKinds.ORCHESTRATOR_DECISION: {
        // Ensure execution analytics remains visible during orchestration planning.
        set((state) => ({
          bottomDrawerTab: "timeline",
          bottomDrawerOpen: true,
          runProgress: {
            ...state.runProgress,
            currentStep: reportedCurrentStep || "orchestrator_planning",
            overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
            lastEventKind: event.kind,
            lastUpdateAt: event.ts,
          },
        }));
        break;
      }

      case EventKinds.WORKFLOW_STATUS: {
        const executorId = payloadString(payload, "executor_id");
        const workflowState = payloadString(payload, "workflowState");
        set((state) => ({
          agents: executorId && state.agents[executorId]
            ? {
                ...state.agents,
                [executorId]: incrementAgentTrace(state.agents[executorId], event.ts),
              }
            : state.agents,
          runProgress: {
            ...state.runProgress,
            currentStep: reportedCurrentStep || workflowState || payloadString(payload, "status", "workflow_status"),
            overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
            lastEventKind: event.kind,
            lastUpdateAt: event.ts,
          },
        }));
        break;
      }

      case EventKinds.PROGRESS_UPDATE: {
        set((state) => ({
          runProgress: {
            ...state.runProgress,
            overallPct: reportedRunPct >= 0 ? reportedRunPct : state.runProgress.overallPct,
            agentsTotal: payloadNumber(payload, "agentsTotal", state.runProgress.agentsTotal),
            agentsActivated: payloadNumber(payload, "agentsActivated", state.runProgress.agentsActivated),
            agentsRunning: payloadNumber(payload, "agentsRunning", state.runProgress.agentsRunning),
            agentsDone: payloadNumber(payload, "agentsDone", state.runProgress.agentsDone),
            agentsErrored: payloadNumber(payload, "agentsErrored", state.runProgress.agentsErrored),
            currentStep: reportedCurrentStep || state.runProgress.currentStep,
            lastEventKind: event.kind,
            lastUpdateAt: event.ts,
          },
        }));
        break;
      }

      case EventKinds.RUN_STARTED: {
        set((state) => ({
          runProgress: {
            ...state.runProgress,
            status: "running",
            currentStep: reportedCurrentStep || "run_started",
            overallPct: reportedRunPct >= 0 ? reportedRunPct : Math.max(state.runProgress.overallPct, 1),
            lastEventKind: event.kind,
            lastUpdateAt: event.ts,
          },
        }));
        break;
      }

      case EventKinds.RUN_COMPLETED: {
        set((state) => ({
          runProgress: {
            ...state.runProgress,
            status: "completed",
            overallPct: 100,
            agentsRunning: 0,
            currentStep: "run_completed",
            lastEventKind: event.kind,
            lastUpdateAt: event.ts,
            isStale: false,
          },
          noUpdateWarning: false,
        }));
        break;
      }

      case EventKinds.RUN_FAILED: {
        set((state) => ({
          runProgress: {
            ...state.runProgress,
            status: "failed",
            agentsRunning: 0,
            currentStep: "run_failed",
            lastEventKind: event.kind,
            lastUpdateAt: event.ts,
            isStale: false,
          },
          noUpdateWarning: false,
        }));
        break;
      }
    }
  },

  // ── UI actions ──────────────────────────────────────────────
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  setBottomDrawerTab: (tab) => set({ bottomDrawerTab: tab }),
  setBottomDrawerOpen: (open) => set({ bottomDrawerOpen: open }),

  // ── Computed ────────────────────────────────────────────────
  getStageByName: (name) => {
    const state = get();
    return state.currentRun?.stages.find((s) => s.stage_name === name);
  },

  getIncludedAgents: () => {
    return Object.values(get().agents).filter((a) => a.included);
  },

  getExcludedAgents: () => {
    return Object.values(get().agents).filter((a) => !a.included);
  },
}));
