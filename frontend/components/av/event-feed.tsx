"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Info,
  Play,
  Wrench,
  Plane,
  Shield,
  BarChart3,
  Radio,
} from "lucide-react";
import { useAviationStore } from "@/store/aviation-store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { WorkflowEvent } from "@/types/aviation";

const eventConfig: Record<
  string,
  { icon: typeof Info; color: string; label: string }
> = {
  run_started: { icon: Play, color: "text-blue-500", label: "Run Started" },
  run_completed: { icon: CheckCircle2, color: "text-emerald-500", label: "Run Completed" },
  run_failed: { icon: XCircle, color: "text-red-500", label: "Run Failed" },
  stage_started: { icon: Play, color: "text-amber-500", label: "Stage Started" },
  stage_completed: { icon: CheckCircle2, color: "text-emerald-500", label: "Stage Completed" },
  stage_failed: { icon: XCircle, color: "text-red-500", label: "Stage Failed" },
  agent_started: { icon: Plane, color: "text-blue-500", label: "Agent Started" },
  agent_completed: { icon: CheckCircle2, color: "text-emerald-500", label: "Agent Completed" },
  agent_message: { icon: Info, color: "text-blue-400", label: "Agent Message" },
  tool_called: { icon: Wrench, color: "text-purple-500", label: "Tool Called" },
  tool_completed: { icon: CheckCircle2, color: "text-purple-400", label: "Tool Completed" },
  tool_error: { icon: XCircle, color: "text-red-500", label: "Tool Error" },
  decision_made: { icon: BarChart3, color: "text-amber-500", label: "Decision Made" },
  safety_check: { icon: Shield, color: "text-emerald-500", label: "Safety Check" },
  progress_update: { icon: Info, color: "text-muted-foreground", label: "Progress" },
};

const eventFilters = [
  { id: "all", label: "All" },
  { id: "stages", label: "Stages" },
  { id: "agents", label: "Agents" },
  { id: "tools", label: "Tools" },
];

function formatTimestamp(ts: string): string {
  try {
    const date = new Date(ts);
    return date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

export function EventFeed() {
  const { events, isConnected, currentRunId } = useAviationStore();
  const [filter, setFilter] = useState("all");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new events
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  const filteredEvents = useMemo(() => {
    if (filter === "all") return events;
    if (filter === "stages") {
      return events.filter(
        (e) => e.kind.includes("stage") || e.kind.includes("run")
      );
    }
    if (filter === "agents") {
      return events.filter((e) => e.kind.includes("agent") || e.kind.includes("decision"));
    }
    if (filter === "tools") {
      return events.filter((e) => e.kind.includes("tool"));
    }
    return events;
  }, [events, filter]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <Radio className="h-4 w-4 text-muted-foreground" />
          <h3 className="font-semibold text-sm">Event Stream</h3>
          {currentRunId && (
            <Badge variant={isConnected ? "running" : "secondary"} className="text-xs">
              {isConnected ? "Live" : "Disconnected"}
            </Badge>
          )}
        </div>
        <div className="flex gap-1">
          {eventFilters.map((f) => (
            <Button
              key={f.id}
              variant={filter === f.id ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Event List */}
      <ScrollArea className="flex-1">
        <div ref={scrollRef} className="p-4 space-y-2">
          {filteredEvents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
              <Radio className="h-8 w-8 mb-3 opacity-50" />
              <p className="text-sm">No events yet</p>
              <p className="text-xs mt-1">
                Submit a problem to see the multi-agent workflow in action
              </p>
            </div>
          ) : (
            <AnimatePresence mode="popLayout">
              {filteredEvents.map((event) => (
                <EventRow key={event.event_id} event={event} />
              ))}
            </AnimatePresence>
          )}
        </div>
      </ScrollArea>

      {/* Footer Stats */}
      {events.length > 0 && (
        <div className="px-4 py-2 border-t text-xs text-muted-foreground flex items-center justify-between">
          <span>{events.length} events</span>
          <span>
            {filteredEvents.length !== events.length &&
              `Showing ${filteredEvents.length} filtered`}
          </span>
        </div>
      )}
    </div>
  );
}

function EventRow({ event }: { event: WorkflowEvent }) {
  const config = eventConfig[event.kind] || {
    icon: Info,
    color: "text-muted-foreground",
    label: event.kind,
  };
  const Icon = config.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -10 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "flex items-start gap-3 p-3 rounded-lg bg-muted/50 border border-border/50",
        event.level === "error" && "bg-red-500/5 border-red-500/20",
        event.level === "warn" && "bg-amber-500/5 border-amber-500/20"
      )}
    >
      <div className={cn("mt-0.5", config.color)}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{config.label}</span>
          {event.agent_name && (
            <Badge variant="secondary" className="text-xs">
              {event.agent_name}
            </Badge>
          )}
          {event.stage_name && (
            <Badge variant="outline" className="text-xs">
              {event.stage_name}
            </Badge>
          )}
          {event.tool_name && (
            <Badge variant="outline" className="text-xs font-mono">
              {event.tool_name}
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground mt-1">{event.message}</p>
        {event.duration_ms != null && (
          <p className="text-xs text-muted-foreground mt-1">
            Duration: {event.duration_ms}ms
          </p>
        )}
      </div>
      <div className="text-xs text-muted-foreground whitespace-nowrap">
        {formatTimestamp(event.ts)}
      </div>
    </motion.div>
  );
}
