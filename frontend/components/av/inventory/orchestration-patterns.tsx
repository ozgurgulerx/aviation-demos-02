"use client";

import { memo } from "react";

/* ── SVG Flow Diagrams ────────────────────────────────────────── */

function SequentialDiagram() {
  return (
    <svg viewBox="0 0 320 60" className="w-full" fill="none">
      {/* Nodes */}
      <rect x="10" y="18" width="70" height="28" rx="6" fill="hsl(201 90% 54% / 0.15)" stroke="hsl(201 90% 54% / 0.5)" strokeWidth="1.2" />
      <text x="45" y="36" textAnchor="middle" className="fill-[hsl(201,90%,54%)]" fontSize="9" fontWeight="600">Agent A</text>

      <rect x="125" y="18" width="70" height="28" rx="6" fill="hsl(201 90% 54% / 0.15)" stroke="hsl(201 90% 54% / 0.5)" strokeWidth="1.2" />
      <text x="160" y="36" textAnchor="middle" className="fill-[hsl(201,90%,54%)]" fontSize="9" fontWeight="600">Agent B</text>

      <rect x="240" y="18" width="70" height="28" rx="6" fill="hsl(201 90% 54% / 0.15)" stroke="hsl(201 90% 54% / 0.5)" strokeWidth="1.2" />
      <text x="275" y="36" textAnchor="middle" className="fill-[hsl(201,90%,54%)]" fontSize="9" fontWeight="600">Agent C</text>

      {/* Arrows */}
      <line x1="80" y1="32" x2="120" y2="32" stroke="hsl(201 90% 54% / 0.6)" strokeWidth="1.5" markerEnd="url(#arrowSeq)" />
      <line x1="195" y1="32" x2="235" y2="32" stroke="hsl(201 90% 54% / 0.6)" strokeWidth="1.5" markerEnd="url(#arrowSeq)" />

      <defs>
        <marker id="arrowSeq" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="hsl(201 90% 54% / 0.6)" />
        </marker>
      </defs>
    </svg>
  );
}

function HandoffDiagram() {
  const cx = 160, cy = 30;
  const specialists = [
    { x: 40, y: 12, label: "Spec A" },
    { x: 280, y: 12, label: "Spec B" },
    { x: 40, y: 48, label: "Spec C" },
    { x: 280, y: 48, label: "Spec D" },
  ];

  return (
    <svg viewBox="0 0 320 60" className="w-full" fill="none">
      {/* Center coordinator */}
      <rect x={cx - 38} y={cy - 14} width="76" height="28" rx="6" fill="hsl(39 96% 57% / 0.15)" stroke="hsl(39 96% 57% / 0.55)" strokeWidth="1.2" />
      <text x={cx} y={cy + 4} textAnchor="middle" className="fill-[hsl(39,96%,57%)]" fontSize="8" fontWeight="600">Coordinator</text>

      {/* Specialist nodes */}
      {specialists.map((s) => (
        <g key={s.label}>
          <rect x={s.x - 28} y={s.y - 9} width="56" height="18" rx="4" fill="hsl(39 96% 57% / 0.1)" stroke="hsl(39 96% 57% / 0.35)" strokeWidth="1" />
          <text x={s.x} y={s.y + 4} textAnchor="middle" className="fill-[hsl(39,96%,57%,0.8)]" fontSize="7.5" fontWeight="500">{s.label}</text>
          {/* Bidirectional lines */}
          <line
            x1={s.x > cx ? s.x - 28 : s.x + 28}
            y1={s.y}
            x2={s.x > cx ? cx + 38 : cx - 38}
            y2={cy}
            stroke="hsl(39 96% 57% / 0.3)"
            strokeWidth="1"
            strokeDasharray="3 2"
          />
        </g>
      ))}
    </svg>
  );
}

function DeterministicDiagram() {
  return (
    <svg viewBox="0 0 320 72" className="w-full" fill="none">
      {/* Input */}
      <rect x="4" y="26" width="44" height="20" rx="4" fill="hsl(157 82% 40% / 0.12)" stroke="hsl(157 82% 40% / 0.45)" strokeWidth="1" />
      <text x="26" y="39" textAnchor="middle" className="fill-[hsl(157,82%,40%)]" fontSize="7.5" fontWeight="600">Input</text>

      {/* Fork lines */}
      <line x1="48" y1="36" x2="80" y2="12" stroke="hsl(157 82% 40% / 0.4)" strokeWidth="1" />
      <line x1="48" y1="36" x2="80" y2="36" stroke="hsl(157 82% 40% / 0.4)" strokeWidth="1" />
      <line x1="48" y1="36" x2="80" y2="60" stroke="hsl(157 82% 40% / 0.4)" strokeWidth="1" />

      {/* Parallel agents */}
      {[
        { y: 4, label: "Spec A" },
        { y: 28, label: "Spec B" },
        { y: 52, label: "Spec C" },
      ].map((s) => (
        <g key={s.label}>
          <rect x="80" y={s.y} width="56" height="16" rx="4" fill="hsl(157 82% 40% / 0.12)" stroke="hsl(157 82% 40% / 0.4)" strokeWidth="1" />
          <text x="108" y={s.y + 11} textAnchor="middle" className="fill-[hsl(157,82%,40%)]" fontSize="7.5" fontWeight="500">{s.label}</text>
        </g>
      ))}

      {/* Merge lines */}
      <line x1="136" y1="12" x2="168" y2="36" stroke="hsl(157 82% 40% / 0.4)" strokeWidth="1" />
      <line x1="136" y1="36" x2="168" y2="36" stroke="hsl(157 82% 40% / 0.4)" strokeWidth="1" />
      <line x1="136" y1="60" x2="168" y2="36" stroke="hsl(157 82% 40% / 0.4)" strokeWidth="1" />

      {/* Aggregator */}
      <rect x="168" y="24" width="60" height="24" rx="5" fill="hsl(157 82% 40% / 0.12)" stroke="hsl(157 82% 40% / 0.5)" strokeWidth="1.2" />
      <text x="198" y="40" textAnchor="middle" className="fill-[hsl(157,82%,40%)]" fontSize="7.5" fontWeight="600">Aggregator</text>

      {/* Arrow to coordinator */}
      <line x1="228" y1="36" x2="255" y2="36" stroke="hsl(157 82% 40% / 0.5)" strokeWidth="1.2" markerEnd="url(#arrowDet)" />

      {/* Coordinator */}
      <rect x="255" y="22" width="60" height="28" rx="6" fill="hsl(157 82% 40% / 0.15)" stroke="hsl(157 82% 40% / 0.55)" strokeWidth="1.2" />
      <text x="285" y="40" textAnchor="middle" className="fill-[hsl(157,82%,40%)]" fontSize="7.5" fontWeight="600">Coordinator</text>

      <defs>
        <marker id="arrowDet" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="hsl(157 82% 40% / 0.5)" />
        </marker>
      </defs>
    </svg>
  );
}

/* ── Pattern Cards ────────────────────────────────────────────── */

const PATTERNS = [
  {
    id: "sequential",
    title: "Sequential",
    color: "hsl(201 90% 54%)",
    diagram: SequentialDiagram,
    description:
      "Linear pipeline: each agent runs in order, passing context forward. Used for the legacy 3-agent workflow (Flight Analyst → Operations Advisor → Safety Inspector).",
    characteristics: [
      "Latency: O(n) serial",
      "Context accumulates per step",
      "Simple, predictable flow",
    ],
  },
  {
    id: "handoff_llm_directed",
    title: "Handoff (LLM-Directed)",
    color: "hsl(39 96% 57%)",
    diagram: HandoffDiagram,
    description:
      "Star topology: an LLM coordinator dynamically delegates to specialists and synthesizes results. Termination uses keyword detection + safety valve.",
    characteristics: [
      "Dynamic agent selection",
      "Coordinator synthesizes results",
      "Flexible, adaptive routing",
    ],
  },
  {
    id: "deterministic_parallel",
    title: "Deterministic (Parallel)",
    color: "hsl(157 82% 40%)",
    diagram: DeterministicDiagram,
    description:
      "Fan-out/fan-in: all specialists execute concurrently, results are aggregated, then the coordinator synthesizes a final decision. Uses WorkflowBuilder with _SpecialistAggregator.",
    characteristics: [
      "Latency: O(1) parallel",
      "All specialists run concurrently",
      "Deterministic aggregation",
    ],
  },
];

function OrchestrationPatternsInner() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {PATTERNS.map((pattern) => {
        const Diagram = pattern.diagram;
        return (
          <div
            key={pattern.id}
            className="flex flex-col rounded-xl border av-panel-muted p-4"
            style={{ borderColor: `${pattern.color}25` }}
          >
            <h3
              className="text-sm font-semibold"
              style={{ color: pattern.color }}
            >
              {pattern.title}
            </h3>

            <div className="my-3 rounded-lg bg-[hsl(var(--av-shell))] p-3">
              <Diagram />
            </div>

            <p className="text-[11px] leading-relaxed text-muted-foreground">
              {pattern.description}
            </p>

            <div className="mt-3 space-y-1">
              {pattern.characteristics.map((c) => (
                <div
                  key={c}
                  className="flex items-center gap-1.5 text-[10px] text-muted-foreground"
                >
                  <span
                    className="h-1 w-1 shrink-0 rounded-full"
                    style={{ backgroundColor: pattern.color }}
                  />
                  {c}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export const OrchestrationPatterns = memo(OrchestrationPatternsInner);
