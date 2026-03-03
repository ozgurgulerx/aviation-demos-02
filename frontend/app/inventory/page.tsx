"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { Plane, ArrowLeft, Loader2 } from "lucide-react";
import { AgentCard } from "@/components/av/inventory/agent-card";
import { AgentDetailModal } from "@/components/av/inventory/agent-detail-modal";
import { OrchestrationPatterns } from "@/components/av/inventory/orchestration-patterns";
import { cn } from "@/lib/utils";
import type { Agent, InventoryData } from "@/components/av/inventory/agent-card";

const SCENARIO_LABELS: Record<string, string> = {
  hub_disruption: "Hub Disruption",
  predictive_maintenance: "Pred. Maintenance",
  diversion: "Diversion",
  crew_fatigue: "Crew Fatigue",
};

export default function InventoryPage() {
  const [data, setData] = useState<InventoryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    fetch("/api/av/inventory", { signal: ac.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => {
        if (!ac.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, []);

  const highlightedAgentIds = useMemo(() => {
    if (!activeScenario || !data) return new Set<string>();
    const config = data.scenarios[activeScenario];
    if (!config) return new Set<string>();
    return new Set([...config.agents, config.coordinator]);
  }, [activeScenario, data]);

  const grouped = useMemo(() => {
    if (!data) return { specialists: [], coordinators: [], placeholders: [] };
    return {
      specialists: data.agents.filter((a) => a.category === "specialist"),
      coordinators: data.agents.filter((a) => a.category === "coordinator"),
      placeholders: data.agents.filter((a) => a.category === "placeholder"),
    };
  }, [data]);

  const handleCloseModal = useCallback(() => setSelectedAgent(null), []);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-av-sky" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 px-4">
        <p className="text-sm text-av-red">
          Failed to load inventory{error ? `: ${error}` : ""}
        </p>
        <Link
          href="/"
          className="text-xs text-av-sky underline underline-offset-2"
        >
          Back to main
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      {/* Header */}
      <header className="shrink-0 px-3 pb-2 pt-3 md:px-6 md:pt-5">
        <div className="flex h-14 items-center justify-between rounded-2xl px-4 av-panel">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-av-sky/30 bg-av-sky/16">
              <Plane className="h-4 w-4 text-av-sky" />
            </div>
            <div>
              <h1 className="text-sm font-semibold tracking-tight">
                Agent Inventory & Orchestration Patterns
              </h1>
              <p className="hidden text-[10px] uppercase tracking-[0.16em] text-muted-foreground/85 sm:block">
                {data.agents.length} Agents — {Object.keys(data.scenarios).length} Scenarios — {data.orchestrationPatterns.length} Patterns
              </p>
            </div>
          </div>
          <Link
            href="/"
            className="flex items-center gap-1.5 rounded-lg border border-av-sky/35 bg-av-sky/10 px-3 py-1.5 text-xs font-semibold text-av-sky transition hover:bg-av-sky/20"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="av-scroll flex-1 overflow-y-auto px-3 pb-8 md:px-6">
        {/* ── Orchestration Patterns ─────────────────────────── */}
        <section className="mt-4">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Orchestration Patterns
          </h2>
          <OrchestrationPatterns />
        </section>

        {/* ── Scenario Coverage ──────────────────────────────── */}
        <section className="mt-6">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Scenario Coverage
          </h2>
          <div className="flex flex-wrap gap-2">
            {Object.entries(SCENARIO_LABELS).map(([id, label]) => {
              const isActive = activeScenario === id;
              const config = data.scenarios[id];
              const agentCount = config
                ? config.agents.length + 1
                : 0;
              return (
                <button
                  key={id}
                  onClick={() =>
                    setActiveScenario(isActive ? null : id)
                  }
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-semibold transition",
                    isActive
                      ? "border-av-sky/40 bg-av-sky/15 text-av-sky"
                      : "border-border/60 text-muted-foreground hover:border-av-sky/30 hover:text-foreground",
                  )}
                >
                  {label}
                  <span
                    className={cn(
                      "rounded-full px-1.5 py-[1px] text-[9px]",
                      isActive
                        ? "bg-av-sky/20 text-av-sky"
                        : "bg-muted/40 text-muted-foreground",
                    )}
                  >
                    {agentCount}
                  </span>
                </button>
              );
            })}
            {activeScenario && (
              <button
                onClick={() => setActiveScenario(null)}
                className="text-[10px] text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Clear filter
              </button>
            )}
          </div>
        </section>

        {/* ── Agent Grid ─────────────────────────────────────── */}
        <section className="mt-6">
          {/* Specialists */}
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Specialists
            <span className="ml-1.5 text-[10px] font-normal text-muted-foreground/60">
              ({grouped.specialists.length})
            </span>
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {grouped.specialists.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                highlighted={
                  activeScenario !== null &&
                  highlightedAgentIds.has(agent.id)
                }
                onClick={() => setSelectedAgent(agent)}
              />
            ))}
          </div>

          {/* Coordinators */}
          <h2 className="mb-3 mt-6 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Coordinators
            <span className="ml-1.5 text-[10px] font-normal text-muted-foreground/60">
              ({grouped.coordinators.length})
            </span>
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {grouped.coordinators.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                highlighted={
                  activeScenario !== null &&
                  highlightedAgentIds.has(agent.id)
                }
                onClick={() => setSelectedAgent(agent)}
              />
            ))}
          </div>

          {/* Placeholders */}
          <h2 className="mb-3 mt-6 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Phase 2 — Placeholders
            <span className="ml-1.5 text-[10px] font-normal text-muted-foreground/60">
              ({grouped.placeholders.length})
            </span>
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {grouped.placeholders.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                highlighted={false}
                onClick={() => setSelectedAgent(agent)}
              />
            ))}
          </div>
        </section>
      </main>

      {/* Agent Detail Modal */}
      <AgentDetailModal
        agent={selectedAgent}
        onClose={handleCloseModal}
        scenarios={data.scenarios}
        allAgents={data.agents}
      />
    </div>
  );
}
