"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Radar, PlaneTakeoff, Users, Network, CloudLightning, UserCheck,
  Wrench, Moon, Navigation, Shield, Satellite, CheckCircle2,
  AlertCircle, Loader2, Database,
  Route, Fuel, DoorOpen, Radio, History, Building, DollarSign,
} from "lucide-react";
import type { AgentStatus } from "@/types/aviation";
import { useAviationStore } from "@/store/aviation-store";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  Radar, PlaneTakeoff, Users, Network, CloudLightning, UserCheck,
  Wrench, Moon, Navigation, Shield, Satellite, Database,
  Route, Fuel, DoorOpen, Radio, History, Building, DollarSign,
};

interface AgentData {
  label: string;
  agentId: string;
  icon: string;
  color: string;
  status: AgentStatus;
  dataSources: string[];
  evidenceCount: number;
  activeQuery?: string;
  currentObjective?: string;
  activeQuerySummary?: string;
  confidence?: number;
  traceCount?: number;
  lastEvidencePreview?: string;
  entryDelay?: number;
  [key: string]: unknown;
}

const DATA_SOURCE_META: Record<string, { provider: "Azure" | "Fabric" | "Other"; tone: string }> = {
  SQL: { provider: "Azure", tone: "hsl(var(--av-azure))" },
  NOSQL: { provider: "Azure", tone: "hsl(var(--av-azure))" },
  VECTOR_OPS: { provider: "Azure", tone: "hsl(var(--av-azure))" },
  VECTOR_REG: { provider: "Azure", tone: "hsl(var(--av-azure))" },
  VECTOR_AIRPORT: { provider: "Azure", tone: "hsl(var(--av-azure))" },
  KQL: { provider: "Fabric", tone: "hsl(var(--av-fabric))" },
  GRAPH: { provider: "Fabric", tone: "hsl(var(--av-fabric))" },
  FABRIC_SQL: { provider: "Fabric", tone: "hsl(var(--av-fabric))" },
};

function AgentNodeInner({ data }: NodeProps & { data: AgentData }) {
  const setSelectedAgent = useAviationStore((s) => s.setSelectedAgent);
  const Icon = ICONS[data.icon] || Radar;
  const isThinking = data.status === "thinking";
  const isQuerying = data.status === "querying";
  const isDone = data.status === "done";
  const isError = data.status === "error";
  const isActive = isThinking || isQuerying;

  const activityText = data.activeQuerySummary || data.currentObjective;

  return (
    <motion.div
      initial={{ scale: 0.75, opacity: 0, y: -12 }}
      animate={{
        scale: data.status === "activated" ? [1, 1.08, 1] : 1,
        opacity: 1,
        y: 0,
      }}
      whileHover={{ scale: 1.03 }}
      transition={{ duration: 0.45, delay: data.entryDelay ?? 0 }}
      onClick={() => setSelectedAgent(data.agentId)}
      className="cursor-pointer relative"
    >
      {/* Outer glow ring when active */}
      {isActive && (
        <motion.div
          className="absolute inset-[-8px] rounded-2xl pointer-events-none"
          style={{
            background: `radial-gradient(ellipse at center, ${data.color}18 0%, transparent 70%)`,
            border: `1.5px solid ${data.color}30`,
          }}
          animate={{ opacity: [0.4, 0.8, 0.4] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
      )}

      {/* Main card */}
      <motion.div
        animate={isError ? { x: [0, -3, 3, -3, 3, 0] } : {}}
        transition={isError ? { duration: 0.4 } : {}}
        className="w-[252px] rounded-xl border bg-av-midnight/92 shadow-lg relative z-10 overflow-hidden transition-all hover:shadow-xl"
        style={{
          borderColor: isDone
            ? "hsl(var(--av-green))"
            : isError
            ? "hsl(var(--av-red))"
            : isActive
            ? data.color
            : `${data.color}40`,
        }}
      >
        {/* Scan-line overlay when thinking */}
        {isThinking && (
          <div className="absolute inset-0 pointer-events-none z-20 overflow-hidden rounded-xl">
            <div
              className="absolute left-0 right-0 h-8 av-scan-line"
              style={{
                background: `linear-gradient(180deg, transparent, ${data.color}10, transparent)`,
              }}
            />
          </div>
        )}

        {/* 1. Header row */}
        <div className="flex items-center gap-2.5 p-3 pb-2">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
            style={{ backgroundColor: `${data.color}20` }}
          >
            <span style={{ color: data.color }}>
              {isQuerying ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Icon className="w-4 h-4" />
              )}
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold truncate leading-tight">{data.label}</p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{
                  backgroundColor: isDone
                    ? "hsl(var(--av-green))"
                    : isError
                    ? "hsl(var(--av-red))"
                    : isActive
                    ? data.color
                    : "hsl(var(--av-silver))",
                }}
              />
              <p className="text-[10px] text-muted-foreground capitalize">{data.status}</p>
            </div>
          </div>
          {/* Evidence count pill */}
          {data.evidenceCount > 0 && (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 400, damping: 15 }}
              className="px-1.5 py-0.5 rounded-full text-[9px] font-bold"
              style={{
                backgroundColor: `${data.color}20`,
                color: data.color,
              }}
            >
              {data.evidenceCount}
            </motion.div>
          )}
        </div>

        <div className="px-3 pb-2 flex items-center justify-between text-[9px] text-muted-foreground">
          <span className="font-mono">traces {data.traceCount ?? 0}</span>
          {data.lastEvidencePreview && (
            <span className="max-w-[120px] truncate" title={data.lastEvidencePreview}>
              {data.lastEvidencePreview}
            </span>
          )}
        </div>

        {/* 2. Activity row (animated in/out) */}
        <AnimatePresence>
          {activityText && isActive && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="px-3 overflow-hidden"
            >
              <div
                className="text-[10px] text-muted-foreground leading-snug px-2 py-1.5 rounded-md mb-2 line-clamp-2"
                style={{ backgroundColor: `${data.color}08`, border: `1px solid ${data.color}15` }}
              >
                {activityText}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* 3. Data source pills */}
        <div className="px-3 pb-1">
          <p className="mb-1 text-[8px] uppercase tracking-wider text-muted-foreground/80">Assigned Datastores</p>
        </div>
        <div className="flex gap-1 px-3 pb-2 flex-wrap">
          {data.dataSources.map((ds) => {
            const isActiveDs = data.activeQuery === ds;
            const meta = DATA_SOURCE_META[ds] || { provider: "Other", tone: "hsl(var(--av-silver))" };
            return (
              <span
                key={ds}
                className="inline-flex items-center gap-1 text-[8px] font-semibold px-1.5 py-0.5 rounded tracking-wide"
                style={{
                  backgroundColor: isActiveDs ? `${data.color}20` : `${meta.tone}12`,
                  color: isActiveDs ? data.color : meta.tone,
                  border: isActiveDs ? `1px solid ${data.color}40` : `1px solid ${meta.tone}35`,
                }}
                title={`${ds} • ${meta.provider}`}
              >
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ backgroundColor: meta.tone, opacity: isActiveDs ? 1 : 0.7 }}
                />
                {ds}
                <span className="text-[7px] opacity-70">{meta.provider}</span>
              </span>
            );
          })}
        </div>

        {/* 4. Confidence bar (when available) */}
        {data.confidence != null && data.confidence > 0 && (
          <div className="px-3 pb-2.5">
            <div className="flex items-center justify-between text-[9px] text-muted-foreground mb-0.5">
              <span>Confidence</span>
              <span>{Math.round(data.confidence * 100)}%</span>
            </div>
            <div className="h-1 bg-muted rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${data.confidence * 100}%` }}
                transition={{ duration: 0.6, ease: "easeOut" }}
                className="h-full rounded-full"
                style={{ backgroundColor: data.color }}
              />
            </div>
          </div>
        )}

        {/* Status icons */}
        {isDone && (
          <CheckCircle2
            className="absolute top-2 right-2 w-4 h-4 z-20"
            style={{ color: "hsl(var(--av-green))" }}
          />
        )}
        {isError && (
          <AlertCircle
            className="absolute top-2 right-2 w-4 h-4 z-20"
            style={{ color: "hsl(var(--av-red))" }}
          />
        )}
      </motion.div>

      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0 !w-2 !h-2" />
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-2 !h-2" />
    </motion.div>
  );
}

export const AgentNode = memo(AgentNodeInner);
