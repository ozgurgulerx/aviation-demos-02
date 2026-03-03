"use client";

import { memo, useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as Tabs from "@radix-ui/react-tabs";
import { X, Terminal, Wrench, Database, Map, FileOutput } from "lucide-react";
import { cn } from "@/lib/utils";
import { SOURCE_COLORS } from "@/lib/aviation-constants";
import type { Agent, ScenarioConfig } from "./agent-card";

const SOURCE_DESCRIPTIONS: Record<string, string> = {
  SQL: "Azure PostgreSQL — flight schedules, aircraft, crew, passenger data",
  KQL: "Microsoft Fabric KQL — real-time ADS-B positions, SIGMETs, weather hazards",
  GRAPH: "Microsoft Fabric Graph — airport/route network, connectivity, cascade paths",
  VECTOR_OPS: "Azure AI Search — operational documents, ASRS safety reports",
  VECTOR_REG: "Azure AI Search — FAA/ICAO regulations, FARs, compliance docs",
  VECTOR_AIRPORT: "Azure AI Search — airport operational profiles and procedures",
  NOSQL: "Azure Cosmos DB — NOTAMs, real-time operational events",
  FABRIC_SQL: "Microsoft Fabric SQL — historical BTS delay data, analytics warehouse",
};

interface AgentDetailModalProps {
  agent: Agent | null;
  onClose: () => void;
  scenarios: Record<string, ScenarioConfig>;
  allAgents: Agent[];
  initialTab?: string;
}

const TAB_ITEMS = [
  { id: "prompt", label: "Prompt", icon: Terminal },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "outputs", label: "Outputs", icon: FileOutput },
  { id: "datasources", label: "Data Sources", icon: Database },
  { id: "scenarios", label: "Scenarios", icon: Map },
] as const;

function AgentDetailModalInner({ agent, onClose, scenarios, allAgents, initialTab }: AgentDetailModalProps) {
  const [activeTab, setActiveTab] = useState(initialTab || "prompt");

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!agent) return;
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [agent, handleKeyDown]);

  // Lock body scroll when modal is open
  useEffect(() => {
    if (!agent) return;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, [agent]);

  // Reset tab when agent changes
  useEffect(() => {
    setActiveTab(initialTab || "prompt");
  }, [agent?.id, initialTab]);

  const agentScenarios = Object.entries(scenarios).filter(
    ([, config]) =>
      config.agents.includes(agent?.id ?? "") || config.coordinator === agent?.id,
  );

  return (
    <AnimatePresence>
      {agent && (
        <motion.div
          key="modal-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={(e) => {
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <motion.div
            key={agent.id}
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 12 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="relative flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-av-sky/20 bg-av-midnight shadow-2xl"
          >
            {/* Header */}
            <div
              className="shrink-0 border-b border-av-sky/20 px-5 py-4"
              style={{
                background: `linear-gradient(135deg, ${agent.color}14 0%, transparent 65%)`,
              }}
            >
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-semibold">{agent.name}</h2>
                  <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span
                      className="rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize"
                      style={{
                        backgroundColor: `${agent.color}18`,
                        color: agent.color,
                      }}
                    >
                      {agent.category}
                    </span>
                    <span>Phase {agent.phase}</span>
                    <span>Priority {agent.priority}</span>
                    <span className="font-mono">{agent.modelTier}</span>
                  </div>
                </div>
                <button
                  onClick={onClose}
                  className="rounded-lg p-1.5 hover:bg-accent"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Tabs */}
            <Tabs.Root
              value={activeTab}
              onValueChange={setActiveTab}
              className="flex min-h-0 flex-1 flex-col"
            >
              <Tabs.List className="flex shrink-0 gap-1 border-b border-av-sky/15 bg-av-midnight/65 px-3 py-1.5">
                {TAB_ITEMS.map((tab) => {
                  const TabIcon = tab.icon;
                  return (
                    <Tabs.Trigger
                      key={tab.id}
                      value={tab.id}
                      className={cn(
                        "flex items-center gap-1.5 rounded-md border border-transparent px-2.5 py-1 text-[11px] font-semibold text-muted-foreground transition",
                        "data-[state=active]:border-av-sky/25 data-[state=active]:bg-av-sky/10 data-[state=active]:text-av-sky",
                      )}
                    >
                      <TabIcon className="h-3 w-3" />
                      {tab.label}
                    </Tabs.Trigger>
                  );
                })}
              </Tabs.List>

              <div className="av-scroll min-h-0 flex-1 overflow-y-auto">
                {/* Prompt tab */}
                <Tabs.Content value="prompt" className="p-4">
                  {agent.instructions ? (
                    <div className="rounded-lg border border-av-sky/14 bg-[hsl(var(--av-shell))] p-4">
                      <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-foreground/90">
                        {agent.instructions}
                      </pre>
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      This agent is planned for Phase 2. System prompt and behavioral instructions will be defined during implementation.
                    </p>
                  )}
                </Tabs.Content>

                {/* Tools tab */}
                <Tabs.Content value="tools" className="space-y-3 p-4">
                  {agent.tools.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      This agent is planned for Phase 2. Tool functions will be implemented based on the assigned data sources.
                    </p>
                  ) : (
                    agent.tools.map((tool) => (
                      <div
                        key={tool.name}
                        className="rounded-lg border border-av-sky/14 bg-av-surface/56 p-3"
                      >
                        <p className="font-mono text-xs font-semibold" style={{ color: agent.color }}>
                          {tool.name}
                        </p>
                        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                          {tool.description}
                        </p>
                        {tool.parameters.length > 0 && (
                          <div className="mt-2 space-y-1">
                            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
                              Parameters
                            </p>
                            {tool.parameters.map((p) => (
                              <div
                                key={p.name}
                                className="flex items-baseline gap-2 rounded bg-muted/25 px-2 py-1 text-[11px]"
                              >
                                <span className="font-mono font-semibold text-foreground/90">
                                  {p.name}
                                </span>
                                <span className="text-[10px] text-muted-foreground">
                                  {p.type}
                                </span>
                                {p.default && (
                                  <span className="text-[10px] text-muted-foreground/60">
                                    = {p.default}
                                  </span>
                                )}
                                {p.description && (
                                  <span className="text-[10px] text-muted-foreground">
                                    — {p.description}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </Tabs.Content>

                {/* Outputs tab */}
                <Tabs.Content value="outputs" className="space-y-2 p-4">
                  {agent.outputs && agent.outputs.length > 0 ? (
                    agent.outputs.map((output) => (
                      <div
                        key={output}
                        className="flex items-start gap-3 rounded-lg border border-av-sky/14 bg-av-surface/56 p-3"
                      >
                        <div
                          className="mt-0.5 w-1.5 shrink-0 rounded-full"
                          style={{ backgroundColor: agent.color, minHeight: 24 }}
                        />
                        <p className="text-xs leading-relaxed text-foreground/90">
                          {output}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Outputs will be defined during Phase 2 implementation.
                    </p>
                  )}
                </Tabs.Content>

                {/* Data Sources tab */}
                <Tabs.Content value="datasources" className="space-y-3 p-4">
                  {agent.dataSources.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      No data sources assigned (coordinator agent).
                    </p>
                  ) : (
                    agent.dataSources.map((ds) => (
                      <div
                        key={ds}
                        className="flex items-start gap-3 rounded-lg border bg-av-surface/56 p-3"
                        style={{ borderColor: `${SOURCE_COLORS[ds] || "#666"}30` }}
                      >
                        <div
                          className="mt-0.5 h-full w-1.5 shrink-0 rounded-full"
                          style={{
                            backgroundColor: SOURCE_COLORS[ds] || "#666",
                            minHeight: 32,
                          }}
                        />
                        <div>
                          <p
                            className="text-xs font-semibold"
                            style={{ color: SOURCE_COLORS[ds] || "#666" }}
                          >
                            {ds}
                          </p>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">
                            {SOURCE_DESCRIPTIONS[ds] || "Data source"}
                          </p>
                        </div>
                      </div>
                    ))
                  )}
                </Tabs.Content>

                {/* Scenarios tab */}
                <Tabs.Content value="scenarios" className="space-y-3 p-4">
                  {agentScenarios.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      Not assigned to any active scenarios.
                    </p>
                  ) : (
                    agentScenarios.map(([scenarioId, config]) => {
                      const isCoordinator = config.coordinator === agent.id;
                      return (
                        <div
                          key={scenarioId}
                          className="rounded-lg border border-av-sky/14 bg-av-surface/56 p-3"
                        >
                          <div className="flex items-center gap-2">
                            <p className="text-xs font-semibold capitalize text-foreground">
                              {scenarioId.replace(/_/g, " ")}
                            </p>
                            {isCoordinator && (
                              <span className="rounded-full bg-av-gold/15 px-2 py-0.5 text-[9px] font-semibold text-av-gold">
                                Coordinator
                              </span>
                            )}
                          </div>
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {[...config.agents, config.coordinator].map((agentId) => {
                              const a = allAgents.find((x) => x.id === agentId);
                              if (!a) return null;
                              const isSelf = a.id === agent.id;
                              return (
                                <span
                                  key={agentId}
                                  className={cn(
                                    "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                                    isSelf
                                      ? "border-current/30 bg-current/10 font-semibold"
                                      : "border-border/50 text-muted-foreground",
                                  )}
                                  style={isSelf ? { color: a.color } : undefined}
                                >
                                  {a.shortName}
                                </span>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })
                  )}
                </Tabs.Content>
              </div>
            </Tabs.Root>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export const AgentDetailModal = memo(AgentDetailModalInner);
