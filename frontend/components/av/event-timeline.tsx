"use client";

import { useMemo, useRef, useEffect, memo } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, XCircle, Play, Info, Wrench, Plane, Shield, BarChart3, Blend, Database } from "lucide-react";
import { useAviationStore } from "@/store/aviation-store";
import { EventKinds, payloadString, payloadNumber } from "@/types/aviation";
import { cn } from "@/lib/utils";

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
};

function formatTime(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return ts;
  }
}

function EventTimelineInner() {
  const events = useAviationStore((s) => s.events);
  const scrollRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(
    () => events.filter((event) => event.kind !== EventKinds.HEARTBEAT),
    [events]
  );

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [filtered.length]);

  if (filtered.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <p className="text-xs">Timeline populates from agent-framework SSE events</p>
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="av-scroll h-full space-y-1 overflow-y-auto px-3 py-2">
      {filtered.map((event, i) => {
        const cfg = EVENT_ICONS[event.kind] || { icon: Info, color: "text-muted-foreground" };
        const Icon = cfg.icon;
        const isLatest = i === filtered.length - 1;
        const payload = event.payload || {};
        const sourceType = payloadString(payload, "sourceType");
        const provider = payloadString(payload, "sourceProvider");
        const resultCount = payloadNumber(payload, "resultCount");

        return (
          <motion.div
            key={event.event_id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.18 }}
            className={cn(
              "flex items-start gap-2 rounded-md border border-transparent px-2 py-1.5",
              isLatest && "border-av-sky/24 bg-av-sky/10"
            )}
          >
            <span className="text-[10px] text-muted-foreground font-mono w-16 shrink-0 mt-0.5">
              {formatTime(event.ts)}
            </span>
            <Icon className={cn("w-3.5 h-3.5 shrink-0 mt-0.5", cfg.color)} />
            <div className="flex-1 min-w-0">
              <p className="text-[11px] leading-snug">{event.message}</p>
              {(sourceType || provider || resultCount > 0) && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {sourceType && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-muted/40 text-muted-foreground">{sourceType}</span>
                  )}
                  {provider && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-av-fabric/15 text-av-fabric">{provider}</span>
                  )}
                  {resultCount > 0 && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-av-azure/15 text-av-azure">{resultCount} rows</span>
                  )}
                </div>
              )}
            </div>
            {event.duration_ms != null && (
              <span className="text-[10px] text-muted-foreground shrink-0 mt-0.5">{event.duration_ms}ms</span>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}

export const EventTimeline = memo(EventTimelineInner);
