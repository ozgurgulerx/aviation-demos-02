"use client";

import { useRef, useEffect, memo, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, Database, Blend } from "lucide-react";
import { useAviationStore } from "@/store/aviation-store";
import type { WorkflowEvent } from "@/types/aviation";
import { EventKinds, payloadNumber, payloadString } from "@/types/aviation";

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

function getAgentDisplayName(agents: Record<string, { name: string }>, agentId: string): string {
  return agents[agentId]?.name || agentId;
}

function describeEvent(
  event: WorkflowEvent,
  agents: Record<string, { name: string; color: string }>
): { title: string; body: string; details: string[]; color: string; expandable?: string } {
  const payload = event.payload || {};
  const agentId = payloadString(payload, "agentId") || payloadString(payload, "executor_id") || event.agent_name || "";
  const agentName = agentId ? getAgentDisplayName(agents, agentId) : "Orchestrator";
  const color = agentId && agents[agentId]?.color ? agents[agentId].color : "hsl(var(--av-sky))";
  const sourceType = payloadString(payload, "sourceType");
  const provider = payloadString(payload, "sourceProvider");
  const latency = payloadNumber(payload, "latencyMs");
  const resultCount = payloadNumber(payload, "resultCount");
  const confidence = payloadNumber(payload, "confidence");
  const objective = payloadString(payload, "objective");
  const querySummary = payloadString(payload, "querySummary");
  const recommendation = payloadString(payload, "recommendation");

  switch (event.kind) {
    case EventKinds.ORCHESTRATOR_PLAN:
      return {
        title: "Execution plan generated",
        body: event.message,
        details: ["multi-agent routing", "scenario detection"],
        color: "hsl(var(--av-gold))",
      };
    case EventKinds.ORCHESTRATOR_DECISION:
      return {
        title: "Coordinator decision",
        body: event.message,
        details: [
          `confidence ${Math.round(payloadNumber(payload, "confidence", 0.9) * 100)}%`,
          payloadString(payload, "decisionType", "decision"),
        ],
        color: "hsl(var(--av-gold))",
      };
    case EventKinds.SPAN_STARTED:
      return {
        title: `${agentName} started`,
        body: objective || event.message,
        details: ["span.started", "agent-framework"],
        color,
      };
    case EventKinds.SPAN_ENDED:
      return {
        title: `${agentName} finished`,
        body: payloadString(payload, "resultSummary", event.message),
        details: [payload.success === false ? "failed" : "completed"],
        color: payload.success === false ? "hsl(var(--av-red))" : color,
      };
    case EventKinds.EXECUTOR_INVOKED:
      return {
        title: `${agentName} invoked`,
        body: objective || event.message,
        details: ["executor", "invoked"],
        color,
      };
    case EventKinds.EXECUTOR_COMPLETED:
      return {
        title: `${agentName} executor complete`,
        body: event.message,
        details: [payloadString(payload, "status", "completed")],
        color,
      };
    case EventKinds.AGENT_OBJECTIVE:
      return {
        title: `${agentName} objective`,
        body: objective || event.message,
        details: [payloadString(payload, "currentStep", "objective")],
        color,
      };
    case EventKinds.AGENT_PROGRESS:
      return {
        title: `${agentName} progress`,
        body: `${Math.round(payloadNumber(payload, "percentComplete", 0))}% complete`,
        details: [payloadString(payload, "currentStep", "streaming")],
        color,
      };
    case EventKinds.AGENT_COMPLETED:
    case EventKinds.AGENT_COMPLETED_LEGACY:
      return {
        title: `${agentName} completed`,
        body: payloadString(payload, "summary", event.message),
        details: [
          payloadString(payload, "completionReason", "completed"),
          `${payloadNumber(payload, "durationMs", 0)}ms`,
        ],
        color: "hsl(var(--av-green))",
      };
    case EventKinds.TOOL_CALLED:
    case EventKinds.TOOL_CALLED_LEGACY:
      return {
        title: `${agentName} tool called`,
        body: payloadString(payload, "toolName", event.message),
        details: ["tool.called"],
        color: "hsl(var(--av-gold))",
      };
    case EventKinds.TOOL_COMPLETED:
    case EventKinds.TOOL_COMPLETED_LEGACY:
      return {
        title: `${agentName} tool completed`,
        body: payloadString(payload, "toolName", event.message),
        details: [`${payloadNumber(payload, "latencyMs", 0)}ms`],
        color: "hsl(var(--av-green))",
      };
    case EventKinds.TOOL_FAILED:
    case EventKinds.TOOL_FAILED_LEGACY:
      return {
        title: `${agentName} tool failed`,
        body: payloadString(payload, "error", event.message),
        details: [payloadString(payload, "toolName", "tool")],
        color: "hsl(var(--av-red))",
      };
    case EventKinds.DATA_SOURCE_QUERY_START:
      return {
        title: `${agentName} querying ${sourceType}`,
        body: querySummary || event.message,
        details: [provider || "unknown provider", payloadString(payload, "queryType", "query")],
        color,
      };
    case EventKinds.DATA_SOURCE_QUERY_COMPLETE:
      return {
        title: `${agentName} received ${resultCount} rows`,
        body: `${sourceType} ${latency}ms`,
        details: [provider || "unknown provider", sourceType, `${latency}ms`],
        color,
        expandable: querySummary,
      };
    case EventKinds.AGENT_EVIDENCE:
      return {
        title: `${agentName} evidence`,
        body: payloadString(payload, "summary", event.message),
        details: [sourceType || "source", `${resultCount} results`, provider || "provider"],
        color,
      };
    case EventKinds.AGENT_RECOMMENDATION:
      return {
        title: `${agentName} recommendation`,
        body: recommendation || event.message,
        details: [`confidence ${Math.round(confidence * 100)}%`],
        color,
        expandable: recommendation,
      };
    case EventKinds.HANDOVER:
      return {
        title: "Agent handover",
        body: `${getAgentDisplayName(agents, payloadString(payload, "fromAgent"))} → ${getAgentDisplayName(agents, payloadString(payload, "toAgent"))}`,
        details: [payloadString(payload, "reason", "delegation")],
        color: "hsl(var(--av-fabric))",
      };
    default:
      return {
        title: event.kind.replaceAll("_", " ").replaceAll(".", " "),
        body: event.message,
        details: [payloadString(payload, "event_type", "workflow")],
        color: "hsl(var(--av-silver))",
      };
  }
}

function ActivityRow({
  event,
  agents,
}: {
  event: WorkflowEvent;
  agents: Record<string, { name: string; color: string }>;
}) {
  const [expanded, setExpanded] = useState(false);
  const described = describeEvent(event, agents);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="group rounded-lg border border-av-sky/16 bg-av-midnight/66 px-3 py-2 transition-colors hover:bg-av-midnight/82"
    >
      <div className="flex items-start gap-2">
        <div
          className="w-1 self-stretch rounded-full shrink-0 mt-0.5"
          style={{ backgroundColor: described.color, minHeight: 30 }}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-muted-foreground">{formatTimestamp(event.ts)}</span>
            <span className="text-[11px] font-semibold">{described.title}</span>
            <span className="text-[9px] uppercase tracking-wider text-muted-foreground bg-muted/50 rounded px-1.5 py-0.5">
              {event.kind}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-foreground/90">{described.body}</p>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {described.details.map((detail, idx) => (
              <span key={`${event.event_id}-detail-${idx}`} className="rounded bg-muted/45 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {detail}
              </span>
            ))}
            {event.kind.includes("data_source") && (
              <span className="inline-flex items-center gap-1 rounded bg-av-azure/15 px-1.5 py-0.5 text-[10px] text-av-azure">
                <Database className="w-3 h-3" />
                datastore trace
              </span>
            )}
            {event.kind.includes("span") && (
              <span className="inline-flex items-center gap-1 rounded bg-av-fabric/15 px-1.5 py-0.5 text-[10px] text-av-fabric">
                <Blend className="w-3 h-3" />
                execution span
              </span>
            )}
          </div>
          {described.expandable && expanded && (
            <p className="text-[10px] text-muted-foreground mt-2 leading-relaxed border-t border-av-sky/10 pt-2">
              {described.expandable}
            </p>
          )}
        </div>
        {described.expandable && (
          <button onClick={() => setExpanded((prev) => !prev)} className="p-1 opacity-70 group-hover:opacity-100 transition-opacity shrink-0">
            <ChevronRight
              className="w-3 h-3 text-muted-foreground transition-transform"
              style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)" }}
            />
          </button>
        )}
      </div>
    </motion.div>
  );
}

function AgentActivityFeedInner() {
  const events = useAviationStore((s) => s.events);
  const agents = useAviationStore((s) => s.agents);
  const scrollRef = useRef<HTMLDivElement>(null);

  const interestingEvents = useMemo(
    () => events.filter((event) => event.kind !== EventKinds.HEARTBEAT),
    [events]
  );

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [interestingEvents.length]);

  if (interestingEvents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <p className="text-xs">SSE agent traces will appear here once execution starts</p>
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="av-scroll h-full space-y-2 overflow-y-auto p-3">
      <AnimatePresence>
        {interestingEvents.map((event) => (
          <ActivityRow key={event.event_id} event={event} agents={agents} />
        ))}
      </AnimatePresence>
    </div>
  );
}

export const AgentActivityFeed = memo(AgentActivityFeedInner);
