"use client";

import {
  Radar, PlaneTakeoff, Users, Network, CloudLightning, UserCheck,
  Wrench, Moon, Navigation, Shield, Satellite, Database,
  Route, Fuel, DoorOpen, Radio, History, Building, DollarSign,
  Brain, Cpu,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { SOURCE_COLORS } from "@/lib/aviation-constants";
import type { ComponentType } from "react";

/* ── Shared types ─────────────────────────────────────────────── */

export interface ToolParam {
  name: string;
  type: string;
  description: string;
  default: string | null;
  required?: boolean;
}

export interface AgentTool {
  name: string;
  description: string;
  parameters: ToolParam[];
}

export interface Agent {
  id: string;
  name: string;
  shortName: string;
  category: string;
  phase: number;
  priority: number;
  icon: string;
  color: string;
  description: string;
  dataSources: string[];
  scenarios: string[];
  outputs: string[];
  instructions: string;
  tools: AgentTool[];
  modelTier: string;
}

export interface ScenarioConfig {
  agents: string[];
  coordinator: string;
}

export interface InventoryData {
  agents: Agent[];
  scenarios: Record<string, ScenarioConfig>;
  orchestrationPatterns: string[];
}

/* ── Icon map ─────────────────────────────────────────────────── */

const ICONS: Record<string, ComponentType<{ className?: string }>> = {
  Radar, PlaneTakeoff, Users, Network, CloudLightning, UserCheck,
  Wrench, Moon, Navigation, Shield, Satellite, Database,
  Route, Fuel, DoorOpen, Radio, History, Building, DollarSign,
  Brain, Cpu,
};

/* ── Agent Card ───────────────────────────────────────────────── */

interface AgentCardProps {
  agent: Agent;
  highlighted: boolean;
  onClick: () => void;
  onDataSourceClick?: (agent: Agent) => void;
}

export function AgentCard({ agent, highlighted, onClick, onDataSourceClick }: AgentCardProps) {
  const Icon = ICONS[agent.icon] || Radar;
  const isPlaceholder = agent.category === "placeholder";

  return (
    <button
      onClick={onClick}
      className={cn(
        "group relative flex w-full flex-col rounded-xl border p-3 text-left transition-all",
        "hover:shadow-lg hover:shadow-black/20",
        isPlaceholder
          ? "border-border/40 bg-av-midnight/40 opacity-60 hover:opacity-80"
          : "av-panel-muted hover:border-current/40",
        highlighted && !isPlaceholder && "ring-1 ring-current/40 shadow-lg shadow-current/10",
      )}
      style={
        !isPlaceholder
          ? { borderColor: highlighted ? `${agent.color}60` : undefined, color: agent.color }
          : undefined
      }
    >
      {/* Top gradient accent */}
      {!isPlaceholder && (
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-[2px] rounded-t-xl"
          style={{ backgroundColor: agent.color }}
        />
      )}

      {/* Header */}
      <div className="flex items-center gap-2.5">
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
          style={{ backgroundColor: isPlaceholder ? "hsl(var(--muted))" : `${agent.color}20` }}
        >
          <span style={{ color: isPlaceholder ? "hsl(var(--muted-foreground))" : agent.color }}>
            <Icon className="h-4 w-4" />
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <p className={cn(
            "truncate text-[11px] font-semibold leading-tight",
            isPlaceholder ? "text-muted-foreground" : "text-foreground",
          )}>
            {agent.name}
          </p>
          <p className="mt-0.5 text-[10px] capitalize text-muted-foreground">
            {agent.category}
          </p>
        </div>
        {agent.tools.length > 0 && (
          <span
            className="shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-bold"
            style={{ backgroundColor: `${agent.color}18`, color: agent.color }}
          >
            {agent.tools.length} tools
          </span>
        )}
      </div>

      {/* Description */}
      <p className="mt-2 line-clamp-2 text-[10px] leading-relaxed text-muted-foreground">
        {agent.description}
      </p>

      {/* Outputs (first 2) */}
      {agent.outputs.length > 0 && (
        <div className="mt-2 space-y-0.5">
          {agent.outputs.slice(0, 2).map((output) => (
            <p
              key={output}
              className="line-clamp-1 flex items-start gap-1 text-[9px] leading-tight text-muted-foreground/80"
            >
              <span className="mt-[3px] h-1 w-1 shrink-0 rounded-full" style={{ backgroundColor: agent.color }} />
              {output}
            </p>
          ))}
        </div>
      )}

      {/* Data source pills */}
      {agent.dataSources.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {agent.dataSources.map((ds) => (
            <button
              key={ds}
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDataSourceClick?.(agent);
              }}
              className="rounded px-1.5 py-[1px] text-[8px] font-semibold tracking-wide transition hover:brightness-125"
              style={{
                backgroundColor: `${SOURCE_COLORS[ds] || "#666"}18`,
                color: SOURCE_COLORS[ds] || "#666",
                border: `1px solid ${SOURCE_COLORS[ds] || "#666"}30`,
              }}
            >
              {ds}
            </button>
          ))}
        </div>
      )}

      {/* Phase badge for placeholders */}
      {isPlaceholder && (
        <span className="mt-2 inline-flex self-start rounded-full border border-border/50 bg-muted/30 px-2 py-0.5 text-[9px] font-medium text-muted-foreground">
          Phase 2 — Planned
        </span>
      )}
    </button>
  );
}
