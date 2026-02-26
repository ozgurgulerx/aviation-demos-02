"use client";

import { memo, useMemo, useRef, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  XCircle,
  Play,
  Info,
  Wrench,
  Plane,
  Shield,
  BarChart3,
  Blend,
  Database,
  Filter,
} from "lucide-react";
import { useAviationStore } from "@/store/aviation-store";
import { EventKinds, payloadString, payloadNumber, type WorkflowEvent } from "@/types/aviation";
import { cn } from "@/lib/utils";

type TimelineFilter = "all" | "lifecycle" | "datastore" | "tools" | "errors" | "completions";

const EVENT_ICONS: Record<string, { icon: typeof Info; color: string }> = {
  [EventKinds.RUN_STARTED]: { icon: Play, color: "text-av-sky" },
  [EventKinds.RUN_COMPLETED]: { icon: CheckCircle2, color: "text-av-green" },
  [EventKinds.RUN_FAILED]: { icon: XCircle, color: "text-av-red" },
  [EventKinds.AGENT_ACTIVATED]: { icon: Plane, color: "text-av-sky" },
  [EventKinds.AGENT_EXCLUDED]: { icon: Plane, color: "text-av-silver" },
  [EventKinds.AGENT_RECOMMENDATION]: { icon: BarChart3, color: "text-av-gold" },
  [EventKinds.SPAN_STARTED]: { icon: Blend, color: "text-av-fabric" },
  [EventKinds.SPAN_ENDED]: { icon: CheckCircle2, color: "text-av-fabric" },
  [EventKinds.HANDOVER]: { icon: Plane, color: "text-av-fabric" },
  [EventKinds.DATA_SOURCE_QUERY_START]: { icon: Wrench, color: "text-av-azure" },
  [EventKinds.DATA_SOURCE_QUERY_COMPLETE]: { icon: Database, color: "text-av-azure" },
  [EventKinds.COORDINATOR_SCORING]: { icon: BarChart3, color: "text-av-gold" },
  [EventKinds.COORDINATOR_PLAN]: { icon: Shield, color: "text-av-green" },
  [EventKinds.ORCHESTRATOR_PLAN]: { icon: Shield, color: "text-av-gold" },
  [EventKinds.ORCHESTRATOR_DECISION]: { icon: Info, color: "text-av-gold" },
  [EventKinds.EXECUTOR_INVOKED]: { icon: Play, color: "text-av-sky" },
  [EventKinds.EXECUTOR_COMPLETED]: { icon: CheckCircle2, color: "text-av-green" },
  [EventKinds.AGENT_OBJECTIVE]: { icon: Info, color: "text-av-sky" },
  [EventKinds.AGENT_PROGRESS]: { icon: Info, color: "text-av-sky" },
  [EventKinds.TOOL_CALLED]: { icon: Wrench, color: "text-av-gold" },
  [EventKinds.TOOL_COMPLETED]: { icon: CheckCircle2, color: "text-av-green" },
  [EventKinds.TOOL_FAILED]: { icon: XCircle, color: "text-av-red" },
  [EventKinds.TOOL_CALLED_LEGACY]: { icon: Wrench, color: "text-av-gold" },
  [EventKinds.TOOL_COMPLETED_LEGACY]: { icon: CheckCircle2, color: "text-av-green" },
  [EventKinds.TOOL_FAILED_LEGACY]: { icon: XCircle, color: "text-av-red" },
};

const FILTERS: Array<{ id: TimelineFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "lifecycle", label: "Lifecycle" },
  { id: "datastore", label: "Datastore" },
  { id: "tools", label: "Tools" },
  { id: "errors", label: "Errors" },
  { id: "completions", label: "Completions" },
];

function formatTime(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return ts;
  }
}

function laneForEvent(event: WorkflowEvent): string {
  const payload = event.payload || {};
  return (
    payloadString(payload, "agentName") ||
    payloadString(payload, "agentId") ||
    payloadString(payload, "executor_name") ||
    payloadString(payload, "executor_id") ||
    event.agent_name ||
    event.executor_name ||
    "Orchestrator"
  );
}

function shouldInclude(event: WorkflowEvent, filter: TimelineFilter): boolean {
  const kind = event.kind;
  if (filter === "all") return true;
  if (filter === "lifecycle") {
    return (
      kind === EventKinds.RUN_STARTED ||
      kind === EventKinds.RUN_COMPLETED ||
      kind === EventKinds.RUN_FAILED ||
      kind === EventKinds.STAGE_STARTED ||
      kind === EventKinds.STAGE_COMPLETED ||
      kind === EventKinds.SPAN_STARTED ||
      kind === EventKinds.SPAN_ENDED ||
      kind === EventKinds.EXECUTOR_INVOKED ||
      kind === EventKinds.EXECUTOR_COMPLETED ||
      kind === EventKinds.AGENT_COMPLETED ||
      kind === EventKinds.AGENT_COMPLETED_LEGACY
    );
  }
  if (filter === "datastore") {
    return kind === EventKinds.DATA_SOURCE_QUERY_START || kind === EventKinds.DATA_SOURCE_QUERY_COMPLETE || kind === EventKinds.AGENT_EVIDENCE;
  }
  if (filter === "tools") {
    return (
      kind === EventKinds.TOOL_CALLED ||
      kind === EventKinds.TOOL_COMPLETED ||
      kind === EventKinds.TOOL_FAILED ||
      kind === EventKinds.TOOL_CALLED_LEGACY ||
      kind === EventKinds.TOOL_COMPLETED_LEGACY ||
      kind === EventKinds.TOOL_FAILED_LEGACY
    );
  }
  if (filter === "errors") {
    return (
      event.level === "error" ||
      kind === EventKinds.RUN_FAILED ||
      kind === EventKinds.STAGE_FAILED ||
      kind === EventKinds.TOOL_FAILED ||
      kind === EventKinds.TOOL_FAILED_LEGACY
    );
  }
  if (filter === "completions") {
    return kind.includes("completed") || kind === EventKinds.SPAN_ENDED || kind === EventKinds.RUN_COMPLETED;
  }
  return true;
}

function EventRow({ event }: { event: WorkflowEvent }) {
  const cfg = EVENT_ICONS[event.kind] || { icon: Info, color: "text-muted-foreground" };
  const Icon = cfg.icon;
  const payload = event.payload || {};
  const sourceType = payloadString(payload, "sourceType");
  const resultCount = payloadNumber(payload, "resultCount");
  const lane = laneForEvent(event);

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.16 }}
      className={cn(
        "flex items-start gap-2 rounded-md border border-transparent px-2 py-1.5",
        event.level === "error" ? "border-av-red/25 bg-av-red/10" : "bg-av-midnight/32"
      )}
    >
      <span className="mt-0.5 w-16 shrink-0 font-mono text-[10px] text-muted-foreground">
        {formatTime(event.ts)}
      </span>
      <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", cfg.color)} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-av-sky/22 bg-av-sky/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-av-sky">
            {lane}
          </span>
          <span className="text-[11px]">{event.message}</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-1">
          <span className="rounded bg-muted/40 px-1.5 py-0.5 text-[9px] text-muted-foreground">{event.kind}</span>
          {sourceType && <span className="rounded bg-av-azure/15 px-1.5 py-0.5 text-[9px] text-av-azure">{sourceType}</span>}
          {resultCount > 0 && <span className="rounded bg-av-fabric/15 px-1.5 py-0.5 text-[9px] text-av-fabric">{resultCount} rows</span>}
        </div>
      </div>
      {event.duration_ms != null && (
        <span className="mt-0.5 shrink-0 text-[10px] text-muted-foreground">{event.duration_ms}ms</span>
      )}
    </motion.div>
  );
}

function EventTimelineInner() {
  const events = useAviationStore((s) => s.events);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState<TimelineFilter>("all");

  const filtered = useMemo(
    () =>
      events.filter((event) => event.kind !== EventKinds.HEARTBEAT).filter((event) => shouldInclude(event, filter)),
    [events, filter]
  );

  const grouped = useMemo(() => {
    const lanes: Record<string, WorkflowEvent[]> = {};
    for (const event of filtered) {
      const lane = laneForEvent(event);
      lanes[lane] = lanes[lane] ? [...lanes[lane], event] : [event];
    }
    return Object.entries(lanes).sort((a, b) => {
      const aTs = Date.parse(a[1][a[1].length - 1]?.ts || "");
      const bTs = Date.parse(b[1][b[1].length - 1]?.ts || "");
      return bTs - aTs;
    });
  }, [filtered]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [filtered.length, filter]);

  if (filtered.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <p className="text-xs">Timeline populates from agent-framework SSE events</p>
      </div>
    );
  }

  return (
    <div className="h-full min-h-0">
      <div className="flex items-center gap-1 border-b border-av-sky/18 px-3 py-1.5">
        <Filter className="h-3.5 w-3.5 text-muted-foreground" />
        {FILTERS.map((item) => (
          <button
            key={item.id}
            onClick={() => setFilter(item.id)}
            className={cn(
              "rounded px-2 py-1 text-[10px] font-semibold transition-colors",
              filter === item.id
                ? "border border-av-sky/25 bg-av-sky/12 text-av-sky"
                : "text-muted-foreground hover:bg-muted/40"
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div ref={scrollRef} className="av-scroll h-[calc(100%-34px)] space-y-2 overflow-y-auto px-3 py-2">
        {grouped.map(([lane, laneEvents]) => (
          <section key={lane} className="space-y-1">
            <div className="sticky top-0 z-[1] rounded-md border border-av-sky/20 bg-av-midnight/80 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {lane}
            </div>
            {laneEvents.map((event) => (
              <EventRow key={event.event_id} event={event} />
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}

export const EventTimeline = memo(EventTimelineInner);
