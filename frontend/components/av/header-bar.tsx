"use client";

import { memo, useMemo } from "react";
import { AlertTriangle, Gauge, Plane, Wifi } from "lucide-react";
import { useAviationStore } from "@/store/aviation-store";
import { cn } from "@/lib/utils";
import { TRACE_V2_ENABLED } from "@/lib/feature-flags";

function timeAgo(ts?: string): string {
  if (!ts) return "n/a";
  const deltaSec = Math.max(0, Math.floor((Date.now() - Date.parse(ts)) / 1000));
  if (deltaSec < 5) return "just now";
  if (deltaSec < 60) return `${deltaSec}s ago`;
  const mins = Math.floor(deltaSec / 60);
  return `${mins}m ago`;
}

function HeaderBarInner() {
  const currentRunId = useAviationStore((s) => s.currentRunId);
  const scenario = useAviationStore((s) => s.scenario);
  const agents = useAviationStore((s) => s.agents);
  const clearEvents = useAviationStore((s) => s.clearEvents);
  const isConnected = useAviationStore((s) => s.isConnected);
  const runProgress = useAviationStore((s) => s.runProgress);
  const noUpdateWarning = useAviationStore((s) => s.noUpdateWarning);

  const includedAgents = useMemo(
    () => Object.values(agents).filter((a) => a.included),
    [agents]
  );

  const progressPct = runProgress.overallPct ?? 0;
  const hasActiveRun = !!currentRunId && runProgress.status === "running";

  return (
    <header className="relative z-20 shrink-0 px-3 pb-2 pt-3 md:px-4 md:pt-4">
      <div className="relative flex h-14 items-center justify-between rounded-2xl px-4 av-panel">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-av-sky/30 bg-av-sky/16">
            <Plane className="h-4 w-4 text-av-sky" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold tracking-tight">Aviation Decision Intelligence</h1>
            <p className="hidden text-[10px] uppercase tracking-[0.16em] text-muted-foreground/85 sm:block">
              Multi-Agent Operations Control
            </p>
          </div>

          {scenario && (
            <span className="av-pill hidden md:inline-flex">
              {scenario.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </span>
          )}

          {currentRunId && (
            <span className="hidden rounded-full border border-border/70 bg-muted/35 px-2 py-0.5 font-mono text-[10px] text-muted-foreground lg:inline-flex">
              run {currentRunId.slice(0, 8)}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2.5">
          {includedAgents.length > 0 && (
            <div className="hidden items-center gap-1 xl:flex">
              {includedAgents.map((agent) => {
                const isActive = agent.status === "thinking" || agent.status === "querying";
                const isDone = agent.status === "done";
                const isError = agent.status === "error";
                return (
                  <div
                    key={agent.id}
                    title={`${agent.name}: ${agent.status}`}
                    className={cn(
                      "flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold tracking-wide transition-all",
                      isDone && "border-av-green/30 text-av-green bg-av-green/10",
                      isError && "border-av-red/30 text-av-red bg-av-red/10",
                      isActive && "border-current bg-current/10",
                      !isDone && !isError && !isActive && "border-border text-muted-foreground"
                    )}
                    style={isActive ? { color: agent.color, borderColor: `${agent.color}40` } : undefined}
                  >
                    <span
                      className={cn(
                        "w-1.5 h-1.5 rounded-full",
                        isActive && "animate-pulse"
                      )}
                      style={{
                        backgroundColor: isDone
                          ? "hsl(var(--av-green))"
                          : isError
                          ? "hsl(var(--av-red))"
                          : agent.color,
                      }}
                    />
                    {agent.shortName || agent.name.split(" ").pop()}
                  </div>
                );
              })}
            </div>
          )}

          {currentRunId && (
            <div className="flex items-center gap-1 text-[10px]">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  isConnected ? "bg-av-green animate-pulse" : "bg-av-red"
                )}
              />
              <span className="text-muted-foreground">{isConnected ? "Live stream" : "Offline"}</span>
            </div>
          )}

          <button
            onClick={() => clearEvents()}
            className="rounded-lg border border-av-sky/35 bg-av-sky px-3 py-1 text-xs font-semibold text-av-navy transition hover:bg-av-sky/90"
          >
            New Problem
          </button>
        </div>
      </div>

      {TRACE_V2_ENABLED && currentRunId && (
        <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-5">
          <div className="av-panel-muted rounded-xl px-3 py-2">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Run State</p>
            <p className={cn(
              "mt-0.5 text-xs font-semibold capitalize",
              runProgress.status === "completed" && "text-av-green",
              runProgress.status === "failed" && "text-av-red",
              runProgress.status === "running" && "text-av-sky",
            )}>
              {runProgress.status}
            </p>
          </div>
          <div className="av-panel-muted rounded-xl px-3 py-2">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Overall Progress</p>
            <p className="mt-0.5 text-xs font-semibold">{Math.round(progressPct)}%</p>
          </div>
          <div className="av-panel-muted rounded-xl px-3 py-2">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Agents</p>
            <p className="mt-0.5 text-xs font-semibold">
              {runProgress.agentsRunning} running / {runProgress.agentsDone} done / {runProgress.agentsErrored} errors
            </p>
          </div>
          <div className="av-panel-muted rounded-xl px-3 py-2">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Last Update</p>
            <p className="mt-0.5 text-xs font-semibold">{timeAgo(runProgress.lastUpdateAt)}</p>
          </div>
          <div className="av-panel-muted rounded-xl px-3 py-2">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Telemetry</p>
            <p className="mt-0.5 flex items-center gap-1 text-xs font-semibold">
              {noUpdateWarning ? <AlertTriangle className="h-3.5 w-3.5 text-av-gold" /> : <Wifi className="h-3.5 w-3.5 text-av-green" />}
              {noUpdateWarning ? "Stale updates" : "Healthy"}
            </p>
          </div>
        </div>
      )}

      {currentRunId && (
        <div className="pointer-events-none absolute bottom-2 left-3 right-3 h-[2px] bg-transparent md:left-4 md:right-4">
          <div
            className="h-full bg-av-sky transition-all duration-700 ease-out"
            style={{ width: `${Math.min(progressPct, 100)}%` }}
          />
        </div>
      )}

      {TRACE_V2_ENABLED && hasActiveRun && (
        <div className="mt-2 flex items-center gap-1.5 rounded-full border border-av-sky/25 bg-av-sky/10 px-3 py-1 text-[11px] font-medium text-av-sky">
          <Gauge className="h-3.5 w-3.5" />
          {runProgress.currentStep || "processing"}
        </div>
      )}
    </header>
  );
}

export const HeaderBar = memo(HeaderBarInner);
