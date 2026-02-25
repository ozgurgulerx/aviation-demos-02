"use client";

import { memo } from "react";
import { motion } from "framer-motion";
import { ResponsiveContainer, AreaChart, Area } from "recharts";
import { Database, Cloud, Layers } from "lucide-react";
import { useAviationStore } from "@/store/aviation-store";
import { cn } from "@/lib/utils";
import type { DataSourceActivity } from "@/types/aviation";

const SOURCE_ICONS: Record<string, { icon: string; color: string }> = {
  SQL: { icon: "SQL", color: "#38bdf8" },
  KQL: { icon: "KQL", color: "#14b8a6" },
  GRAPH: { icon: "GR", color: "#2dd4bf" },
  VECTOR_OPS: { icon: "OPS", color: "#0ea5e9" },
  VECTOR_REG: { icon: "REG", color: "#0284c7" },
  VECTOR_AIRPORT: { icon: "AIR", color: "#0369a1" },
  NOSQL: { icon: "CS", color: "#2563eb" },
  FABRIC_SQL: { icon: "FSQL", color: "#14b8a6" },
};

function SourceCard({ source }: { source: DataSourceActivity }) {
  const cfg = SOURCE_ICONS[source.type] || { icon: "??", color: "#666" };
  const sparkData = source.sparkline.map((v, i) => ({ i, v }));

  return (
    <motion.div
      key={source.id}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "rounded-xl border p-3 bg-av-midnight/65 transition-all",
        source.isActive && "ring-1 ring-offset-1 ring-offset-av-navy"
      )}
      style={{
        borderColor: source.isActive ? cfg.color : "hsl(var(--border) / 0.6)",
        boxShadow: source.isActive ? `0 0 18px ${cfg.color}33` : undefined,
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center text-[9px] font-bold text-av-navy"
          style={{ backgroundColor: cfg.color }}
        >
          {cfg.icon}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold truncate">{source.name}</p>
          <p className="text-[10px] text-muted-foreground">{source.platformLabel}</p>
        </div>
        {source.isActive && (
          <div className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: cfg.color }} />
        )}
      </div>

      <div className="grid grid-cols-3 gap-1 text-[10px] text-muted-foreground mb-2">
        <span>{source.queryCount} q</span>
        <span>{source.totalResults} rows</span>
        <span>{source.avgLatencyMs}ms</span>
      </div>

      {source.lastQuerySummary && (
        <p className="text-[10px] text-muted-foreground line-clamp-2 mb-2">{source.lastQuerySummary}</p>
      )}

      {sparkData.length > 1 && (
        <div className="h-10">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkData}>
              <Area
                type="monotone"
                dataKey="v"
                stroke={cfg.color}
                fill={cfg.color}
                fillOpacity={0.2}
                strokeWidth={1.5}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </motion.div>
  );
}

function DataSourceActivityViewInner() {
  const dataSources = useAviationStore((s) => s.dataSources);
  const sources = Object.values(dataSources);
  const azureSources = sources.filter((source) => source.provider === "Azure");
  const fabricSources = sources.filter((source) => source.provider === "Fabric");

  const azureTotals = azureSources.reduce(
    (acc, source) => {
      acc.queries += source.queryCount;
      acc.results += source.totalResults;
      return acc;
    },
    { queries: 0, results: 0 }
  );
  const fabricTotals = fabricSources.reduce(
    (acc, source) => {
      acc.queries += source.queryCount;
      acc.results += source.totalResults;
      return acc;
    },
    { queries: 0, results: 0 }
  );

  return (
    <div className="av-scroll h-full space-y-3 overflow-y-auto p-3">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <section className="rounded-xl border border-av-azure/28 bg-av-azure/10 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Cloud className="w-4 h-4 text-av-azure" />
              <h3 className="text-xs font-semibold">Azure Datastores</h3>
            </div>
            <span className="text-[10px] text-av-azure font-mono">
              {azureTotals.queries} queries | {azureTotals.results} rows
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {azureSources.map((source) => (
              <SourceCard key={source.id} source={source} />
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-av-fabric/28 bg-av-fabric/10 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-av-fabric" />
              <h3 className="text-xs font-semibold">Microsoft Fabric Datastores</h3>
            </div>
            <span className="text-[10px] text-av-fabric font-mono">
              {fabricTotals.queries} queries | {fabricTotals.results} rows
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {fabricSources.map((source) => (
              <SourceCard key={source.id} source={source} />
            ))}
          </div>
        </section>
      </div>

      <div className="rounded-xl border border-av-sky/20 bg-av-midnight/70 px-3 py-2 text-[11px] text-muted-foreground flex items-center gap-2">
        <Database className="w-3.5 h-3.5 text-av-sky" />
        Datastore cards are updated from agent-framework SSE trace events (`data_source.query_start` / `data_source.query_complete`).
      </div>
    </div>
  );
}

export const DataSourceActivityView = memo(DataSourceActivityViewInner);
