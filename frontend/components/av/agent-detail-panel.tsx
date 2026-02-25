"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X, Database, CheckCircle2, Loader2, AlertCircle, Blend } from "lucide-react";
import { useAviationStore } from "@/store/aviation-store";
import { Badge } from "@/components/ui/badge";
import { slidePanel } from "@/lib/animation-variants";

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

export function AgentDetailPanel() {
  const { selectedAgentId, agents, setSelectedAgent } = useAviationStore();
  const agent = selectedAgentId ? agents[selectedAgentId] : null;
  if (!agent) return null;

  return (
    <AnimatePresence>
      <motion.div
        key={agent.id}
        variants={slidePanel}
        initial="hidden"
        animate="visible"
        exit="exit"
        className="absolute bottom-3 right-0 top-3 z-30 flex w-[420px] flex-col overflow-hidden rounded-l-2xl border-l border-av-sky/25 bg-av-midnight/94 shadow-2xl"
      >
        <div
          className="flex items-center justify-between px-4 py-3 border-b border-av-sky/20"
          style={{ background: `linear-gradient(135deg, ${agent.color}16 0%, transparent 65%)` }}
        >
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${agent.color}24` }}>
              <Database className="w-4.5 h-4.5" style={{ color: agent.color }} />
            </div>
            <div>
              <h3 className="text-sm font-semibold">{agent.name}</h3>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: agent.color }} />
                <span className="text-[11px] text-muted-foreground capitalize">{agent.status}</span>
                <span className="text-[10px] text-muted-foreground bg-muted/45 rounded px-1.5 py-0.5 font-mono">
                  traces {agent.traceCount ?? 0}
                </span>
              </div>
            </div>
          </div>
          <button onClick={() => setSelectedAgent(null)} className="p-1.5 hover:bg-accent rounded-md" aria-label="Close agent details">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="av-scroll flex-1 overflow-y-auto">
          <div className="px-4 py-3 border-b border-av-sky/15">
            <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-2">Assigned Datastores</p>
            <div className="flex flex-wrap gap-1.5">
              {agent.dataSources.map((source) => (
                <Badge
                  key={source}
                  variant="outline"
                  className="text-[10px] px-2 py-0.5 border"
                  style={{ borderColor: SOURCE_COLORS[source] || "#666", color: SOURCE_COLORS[source] || "#666" }}
                >
                  {source}
                </Badge>
              ))}
            </div>
          </div>

          <div className="px-4 py-3 border-b border-av-sky/15">
            <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-2">
              Evidence Trail ({agent.evidence.length})
            </p>
            {agent.evidence.length === 0 ? (
              <p className="text-xs text-muted-foreground/70">No evidence traces yet</p>
            ) : (
              <div className="space-y-2">
                {agent.evidence.map((ev) => (
                  <div key={ev.id} className="flex items-start gap-2 rounded-md border border-av-sky/12 bg-av-surface/62 p-2">
                    <div
                      className="w-1.5 h-full rounded-full shrink-0 mt-1"
                      style={{ backgroundColor: SOURCE_COLORS[ev.sourceType] || "#666", minHeight: 24 }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-semibold" style={{ color: SOURCE_COLORS[ev.sourceType] }}>
                          {ev.sourceType}
                        </span>
                        <span className="text-[10px] text-muted-foreground">{ev.resultCount} rows</span>
                        <span className="text-[10px] text-muted-foreground font-mono">{new Date(ev.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <p className="text-[11px] text-foreground/85 mt-0.5 line-clamp-2">{ev.summary}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {agent.toolCalls.length > 0 && (
            <div className="px-4 py-3 border-b border-av-sky/15">
              <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-2">
                Tool Calls ({agent.toolCalls.length})
              </p>
              <div className="space-y-1.5">
                {agent.toolCalls.map((tc) => (
                  <div key={tc.id} className="flex items-center gap-2 text-xs">
                    {tc.status === "running" && <Loader2 className="w-3 h-3 animate-spin text-av-gold" />}
                    {tc.status === "done" && <CheckCircle2 className="w-3 h-3 text-av-green" />}
                    {tc.status === "error" && <AlertCircle className="w-3 h-3 text-av-red" />}
                    <span className="font-mono text-[11px]">{tc.toolName}</span>
                    {tc.latencyMs && <span className="text-muted-foreground text-[10px]">{tc.latencyMs}ms</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {agent.recommendation && (
            <div className="px-4 py-3">
              <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1">
                <Blend className="w-3 h-3 text-av-fabric" />
                Recommendation Trace
              </p>
              <div className="p-3 rounded-lg border border-av-fabric/20 bg-av-fabric/8">
                <p className="text-xs leading-relaxed">{agent.recommendation}</p>
                {agent.confidence != null && (
                  <div className="mt-2">
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground mb-1">
                      <span>Confidence</span>
                      <span>{Math.round(agent.confidence * 100)}%</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${agent.confidence * 100}%` }}
                        transition={{ duration: 0.5 }}
                        className="h-full rounded-full"
                        style={{ backgroundColor: agent.color }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
