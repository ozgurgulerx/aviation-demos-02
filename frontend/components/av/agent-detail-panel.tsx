"use client";

import { motion, AnimatePresence } from "framer-motion";
import * as Tabs from "@radix-ui/react-tabs";
import { X, Database, CheckCircle2, Loader2, AlertCircle, Blend } from "lucide-react";
import { useAviationStore } from "@/store/aviation-store";
import { Badge } from "@/components/ui/badge";
import { slidePanel } from "@/lib/animation-variants";
import { payloadString, type WorkflowEvent } from "@/types/aviation";
import { cn } from "@/lib/utils";

const SOURCE_COLORS: Record<string, string> = {
  SQL: "#38bdf8",
  KQL: "#14b8a6",
  GRAPH: "#2dd4bf",
  VECTOR_OPS: "#0ea5e9",
  VECTOR_REG: "#0284c7",
  VECTOR_AIRPORT: "#0369a1",
  NOSQL: "#2563eb",
  FABRIC_SQL: "#14b8a6",
};

const TAB_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "trace", label: "Trace" },
  { id: "datastore", label: "Datastore" },
  { id: "tools", label: "Tools" },
  { id: "evidence", label: "Evidence" },
  { id: "completion", label: "Completion" },
] as const;

function belongsToAgent(event: WorkflowEvent, agentId: string, agentName: string): boolean {
  const payload = event.payload || {};
  return (
    payloadString(payload, "agentId") === agentId ||
    payloadString(payload, "agentName") === agentName ||
    payloadString(payload, "executor_id") === agentId ||
    payloadString(payload, "executor_name") === agentName ||
    event.agent_name === agentName ||
    event.executor_name === agentName
  );
}

export function AgentDetailPanel() {
  const { selectedAgentId, agents, setSelectedAgent, events } = useAviationStore();
  const agent = selectedAgentId ? agents[selectedAgentId] : null;
  if (!agent) return null;

  const agentEvents = events.filter((event) => belongsToAgent(event, agent.id, agent.name)).slice(-120);
  const completionLabel = agent.status === "done" ? "Completed" : agent.status === "error" ? "Failed" : "In Progress";

  return (
    <AnimatePresence>
      <motion.div
        key={agent.id}
        variants={slidePanel}
        initial="hidden"
        animate="visible"
        exit="exit"
        className="absolute bottom-3 right-0 top-3 z-30 flex w-[430px] flex-col overflow-hidden rounded-l-2xl border-l border-av-sky/25 bg-av-midnight/94 shadow-2xl"
      >
        <div
          className="border-b border-av-sky/20 px-4 py-3"
          style={{ background: `linear-gradient(135deg, ${agent.color}16 0%, transparent 65%)` }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg" style={{ backgroundColor: `${agent.color}24` }}>
                <Database className="h-4.5 w-4.5" style={{ color: agent.color }} />
              </div>
              <div>
                <h3 className="text-sm font-semibold">{agent.name}</h3>
                <div className="mt-0.5 flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: agent.color }} />
                  <span className="text-[11px] text-muted-foreground capitalize">{agent.status}</span>
                  <span className="rounded bg-muted/45 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                    traces {agent.traceCount ?? 0}
                  </span>
                </div>
              </div>
            </div>
            <button onClick={() => setSelectedAgent(null)} className="rounded-md p-1.5 hover:bg-accent" aria-label="Close agent details">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <Tabs.Root defaultValue="overview" className="flex min-h-0 flex-1 flex-col">
          <Tabs.List className="flex gap-1 border-b border-av-sky/15 bg-av-midnight/65 px-2 py-1.5">
            {TAB_ITEMS.map((tab) => (
              <Tabs.Trigger
                key={tab.id}
                value={tab.id}
                className={cn(
                  "rounded-md border border-transparent px-2 py-1 text-[10px] font-semibold text-muted-foreground transition",
                  "data-[state=active]:border-av-sky/25 data-[state=active]:bg-av-sky/10 data-[state=active]:text-av-sky"
                )}
              >
                {tab.label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>

          <div className="av-scroll min-h-0 flex-1 overflow-y-auto">
            <Tabs.Content value="overview" className="space-y-3 p-4">
              <div className="rounded-lg border border-av-sky/14 bg-av-surface/56 p-3">
                <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Current Objective</p>
                <p className="mt-1 text-xs leading-relaxed">{agent.currentObjective || "Waiting for next assignment."}</p>
                <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                  <div className="rounded bg-muted/35 px-2 py-1">Step: {agent.currentStep || "n/a"}</div>
                  <div className="rounded bg-muted/35 px-2 py-1">Progress: {Math.round(agent.percentComplete ?? 0)}%</div>
                  <div className="rounded bg-muted/35 px-2 py-1">Started: {agent.startedAt ? new Date(agent.startedAt).toLocaleTimeString() : "n/a"}</div>
                  <div className="rounded bg-muted/35 px-2 py-1">Updated: {agent.lastTraceAt ? new Date(agent.lastTraceAt).toLocaleTimeString() : "n/a"}</div>
                </div>
              </div>
              {agent.recommendation && (
                <div className="rounded-lg border border-av-fabric/20 bg-av-fabric/8 p-3">
                  <p className="mb-2 flex items-center gap-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    <Blend className="h-3 w-3 text-av-fabric" />
                    Latest Recommendation
                  </p>
                  <p className="text-xs leading-relaxed">{agent.recommendation}</p>
                </div>
              )}
            </Tabs.Content>

            <Tabs.Content value="trace" className="space-y-2 p-4">
              {agentEvents.length === 0 ? (
                <p className="text-xs text-muted-foreground">No trace events for this agent yet.</p>
              ) : (
                agentEvents.map((event) => (
                  <div key={event.event_id} className="rounded-md border border-av-sky/12 bg-av-midnight/60 px-2.5 py-2">
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                      <span>{event.kind}</span>
                      <span>{new Date(event.ts).toLocaleTimeString()}</span>
                    </div>
                    <p className="mt-1 text-[11px]">{event.message}</p>
                  </div>
                ))
              )}
            </Tabs.Content>

            <Tabs.Content value="datastore" className="space-y-3 p-4">
              <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Assigned Datastores</p>
              <div className="flex flex-wrap gap-1.5">
                {agent.dataSources.map((source) => (
                  <Badge
                    key={source}
                    variant="outline"
                    className="border px-2 py-0.5 text-[10px]"
                    style={{ borderColor: SOURCE_COLORS[source] || "#666", color: SOURCE_COLORS[source] || "#666" }}
                  >
                    {source}
                  </Badge>
                ))}
              </div>
            </Tabs.Content>

            <Tabs.Content value="tools" className="space-y-2 p-4">
              {agent.toolCalls.length === 0 ? (
                <p className="text-xs text-muted-foreground">No tool invocations recorded yet.</p>
              ) : (
                agent.toolCalls.map((tc) => (
                  <div key={tc.id} className="flex items-center gap-2 rounded-md border border-av-sky/12 bg-av-surface/58 px-2 py-1.5 text-xs">
                    {tc.status === "running" && <Loader2 className="h-3 w-3 animate-spin text-av-gold" />}
                    {tc.status === "done" && <CheckCircle2 className="h-3 w-3 text-av-green" />}
                    {tc.status === "error" && <AlertCircle className="h-3 w-3 text-av-red" />}
                    <span className="font-mono text-[11px]">{tc.toolName}</span>
                    {tc.latencyMs != null && <span className="text-[10px] text-muted-foreground">{tc.latencyMs}ms</span>}
                    {tc.error && <span className="text-[10px] text-av-red">{tc.error}</span>}
                  </div>
                ))
              )}
            </Tabs.Content>

            <Tabs.Content value="evidence" className="space-y-2 p-4">
              {agent.evidence.length === 0 ? (
                <p className="text-xs text-muted-foreground">No evidence traces yet.</p>
              ) : (
                agent.evidence.map((ev) => (
                  <div key={ev.id} className="flex items-start gap-2 rounded-md border border-av-sky/12 bg-av-surface/62 p-2">
                    <div
                      className="mt-1 h-full w-1.5 shrink-0 rounded-full"
                      style={{ backgroundColor: SOURCE_COLORS[ev.sourceType] || "#666", minHeight: 24 }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-semibold" style={{ color: SOURCE_COLORS[ev.sourceType] }}>
                          {ev.sourceType}
                        </span>
                        <span className="text-[10px] text-muted-foreground">{ev.resultCount} rows</span>
                        <span className="font-mono text-[10px] text-muted-foreground">{new Date(ev.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-[11px] text-foreground/85">{ev.summary}</p>
                    </div>
                  </div>
                ))
              )}
            </Tabs.Content>

            <Tabs.Content value="completion" className="space-y-3 p-4">
              <div className="rounded-lg border border-av-sky/18 bg-av-midnight/65 p-3">
                <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Completion Status</p>
                <p className={cn(
                  "mt-1 text-sm font-semibold",
                  agent.status === "done" && "text-av-green",
                  agent.status === "error" && "text-av-red",
                  agent.status !== "done" && agent.status !== "error" && "text-av-sky"
                )}>
                  {completionLabel}
                </p>
                <div className="mt-2 space-y-1 text-[11px]">
                  <p>Reason: {agent.completionReason || "pending"}</p>
                  <p>Started: {agent.startedAt ? new Date(agent.startedAt).toLocaleString() : "n/a"}</p>
                  <p>Ended: {agent.endedAt ? new Date(agent.endedAt).toLocaleString() : "n/a"}</p>
                  <p>Duration: {agent.durationMs != null ? `${agent.durationMs}ms` : "n/a"}</p>
                </div>
              </div>
            </Tabs.Content>
          </div>
        </Tabs.Root>
      </motion.div>
    </AnimatePresence>
  );
}
