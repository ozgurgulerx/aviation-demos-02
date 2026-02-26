"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { motion } from "framer-motion";
import { Brain, Cpu, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import type { AgentStatus } from "@/types/aviation";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = { Brain, Cpu };

interface CoordinatorData {
  label: string;
  icon: string;
  color: string;
  status: AgentStatus;
  agentsCompleted?: number;
  agentsTotal?: number;
  entryDelay?: number;
  [key: string]: unknown;
}

function CoordinatorNodeInner({ data }: NodeProps & { data: CoordinatorData }) {
  const Icon = ICONS[data.icon] || Brain;
  const isActive = data.status === "thinking" || data.status === "querying";
  const isDone = data.status === "done";
  const isError = data.status === "error";
  const completed = data.agentsCompleted ?? 0;
  const total = data.agentsTotal ?? 0;
  const progress = total > 0 ? completed / total : 0;

  // Progress ring math
  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - progress);

  return (
    <motion.div
      initial={{ scale: 0.74, opacity: 0, y: 12 }}
      animate={{
        scale: isDone ? [1, 1.1, 1] : 1,
        opacity: 1,
        y: 0,
      }}
      whileHover={{ scale: 1.05 }}
      transition={{ duration: 0.5, delay: data.entryDelay ?? 0 }}
      className="relative"
    >
      {/* Pulsing gold glow ring */}
      {isActive && (
        <motion.div
          className="absolute inset-[-8px] rounded-full pointer-events-none"
          style={{
            background: "radial-gradient(circle, hsl(var(--av-gold) / 0.15) 0%, transparent 70%)",
            border: "2px solid hsl(var(--av-gold) / 0.3)",
          }}
          animate={{ scale: [1, 1.12, 1], opacity: [0.5, 0.8, 0.5] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
      )}

      {/* Main circle */}
      <div
        className="w-[116px] h-[116px] rounded-full flex flex-col items-center justify-center border-2 bg-av-midnight/95 shadow-lg relative z-10"
        style={{
          borderColor: isDone
            ? "hsl(var(--av-green))"
            : isError
            ? "hsl(var(--av-red))"
            : "hsl(var(--av-gold))",
          boxShadow: isActive ? "0 0 24px hsl(var(--av-gold) / 0.25)" : undefined,
        }}
      >
        {/* Multi-segment progress ring */}
        <svg className="absolute inset-0 w-[116px] h-[116px] -rotate-90" viewBox="0 0 100 100">
          {/* Background track */}
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="hsl(var(--av-silver) / 0.15)"
            strokeWidth="3"
          />
          {/* Progress fill */}
          {total > 0 && (
            <circle
              cx="50"
              cy="50"
              r={radius}
              fill="none"
              stroke="hsl(var(--av-gold))"
              strokeWidth="3"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              strokeLinecap="round"
              className="transition-all duration-700 ease-out"
            />
          )}
          {/* Rotating sweep when active */}
          {isActive && (
            <circle
              cx="50"
              cy="50"
              r={radius}
              fill="none"
              stroke="hsl(var(--av-gold))"
              strokeWidth="2"
              strokeDasharray={`${circumference * 0.15} ${circumference * 0.85}`}
              opacity={0.3}
            >
              <animateTransform
                attributeName="transform"
                type="rotate"
                from="0 50 50"
                to="360 50 50"
                dur="2s"
                repeatCount="indefinite"
              />
            </circle>
          )}
        </svg>

        <span style={{ color: "hsl(var(--av-gold))" }}>
          <Icon className="w-6 h-6 mb-0.5" />
        </span>
        <span className="text-[7px] uppercase tracking-wider text-av-gold/80">Command Core</span>
        <span className="text-[9px] font-semibold text-center leading-tight px-1">{data.label}</span>
        {total > 0 && (
          <span className="text-[8px] text-muted-foreground mt-0.5">
            {completed}/{total}
          </span>
        )}

        {/* Status indicator */}
        {isDone && (
          <CheckCircle2
            className="absolute -bottom-1 -right-1 w-4 h-4 bg-card rounded-full"
            style={{ color: "hsl(var(--av-green))" }}
          />
        )}
        {isError && (
          <AlertCircle
            className="absolute -bottom-1 -right-1 w-4 h-4 bg-card rounded-full"
            style={{ color: "hsl(var(--av-red))" }}
          />
        )}
        {isActive && (
          <Loader2
            className="absolute -bottom-1 -right-1 w-4 h-4 bg-card rounded-full animate-spin"
            style={{ color: "hsl(var(--av-gold))" }}
          />
        )}
      </div>

      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0 !w-3 !h-3" />
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-3 !h-3" />
      <Handle type="source" position={Position.Left} id="left" className="!bg-transparent !border-0 !w-3 !h-3" />
      <Handle type="source" position={Position.Right} id="right" className="!bg-transparent !border-0 !w-3 !h-3" />
    </motion.div>
  );
}

export const CoordinatorNode = memo(CoordinatorNodeInner);
