"use client";

import { memo } from "react";
import { ExternalLink } from "lucide-react";

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

function ConcurrentDiagram() {
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
      <line x1="228" y1="36" x2="255" y2="36" stroke="hsl(157 82% 40% / 0.5)" strokeWidth="1.2" markerEnd="url(#arrowConc)" />

      {/* Coordinator */}
      <rect x="255" y="22" width="60" height="28" rx="6" fill="hsl(157 82% 40% / 0.15)" stroke="hsl(157 82% 40% / 0.55)" strokeWidth="1.2" />
      <text x="285" y="40" textAnchor="middle" className="fill-[hsl(157,82%,40%)]" fontSize="7.5" fontWeight="600">Coordinator</text>

      <defs>
        <marker id="arrowConc" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="hsl(157 82% 40% / 0.5)" />
        </marker>
      </defs>
    </svg>
  );
}

function GroupChatDiagram() {
  return (
    <svg viewBox="0 0 320 72" className="w-full" fill="none">
      {/* Manager node */}
      <rect x="120" y="2" width="80" height="24" rx="6" fill="hsl(270 70% 60% / 0.15)" stroke="hsl(270 70% 60% / 0.55)" strokeWidth="1.2" />
      <text x="160" y="18" textAnchor="middle" className="fill-[hsl(270,70%,60%)]" fontSize="8" fontWeight="600">Manager</text>

      {/* Speaker selection arrow */}
      <line x1="160" y1="26" x2="160" y2="38" stroke="hsl(270 70% 60% / 0.5)" strokeWidth="1.2" markerEnd="url(#arrowGC)" />
      <text x="180" y="35" className="fill-[hsl(270,70%,60%,0.6)]" fontSize="6">selects</text>

      {/* Agent nodes */}
      {[
        { x: 50, label: "Agent A" },
        { x: 160, label: "Agent B" },
        { x: 270, label: "Agent C" },
      ].map((s) => (
        <g key={s.label}>
          <rect x={s.x - 35} y="42" width="70" height="22" rx="5" fill="hsl(270 70% 60% / 0.1)" stroke="hsl(270 70% 60% / 0.35)" strokeWidth="1" />
          <text x={s.x} y="57" textAnchor="middle" className="fill-[hsl(270,70%,60%,0.8)]" fontSize="7.5" fontWeight="500">{s.label}</text>
        </g>
      ))}

      {/* Shared thread arc */}
      <path d="M 50 64 Q 160 80 270 64" stroke="hsl(270 70% 60% / 0.3)" strokeWidth="1" strokeDasharray="4 2" fill="none" />
      <text x="160" y="78" textAnchor="middle" className="fill-[hsl(270,70%,60%,0.4)]" fontSize="5.5">shared thread</text>

      <defs>
        <marker id="arrowGC" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="hsl(270 70% 60% / 0.5)" />
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

function MagenticDiagram() {
  return (
    <svg viewBox="0 0 320 72" className="w-full" fill="none">
      {/* Manager */}
      <rect x="8" y="22" width="68" height="28" rx="6" fill="hsl(340 75% 55% / 0.15)" stroke="hsl(340 75% 55% / 0.55)" strokeWidth="1.2" />
      <text x="42" y="40" textAnchor="middle" className="fill-[hsl(340,75%,55%)]" fontSize="8" fontWeight="600">Manager</text>

      {/* Arrow to ledger */}
      <line x1="76" y1="36" x2="108" y2="36" stroke="hsl(340 75% 55% / 0.5)" strokeWidth="1.2" markerEnd="url(#arrowMag)" />

      {/* Task Ledger */}
      <rect x="108" y="18" width="80" height="36" rx="6" fill="hsl(340 75% 55% / 0.12)" stroke="hsl(340 75% 55% / 0.5)" strokeWidth="1.2" />
      <text x="148" y="34" textAnchor="middle" className="fill-[hsl(340,75%,55%)]" fontSize="7" fontWeight="600">Task</text>
      <text x="148" y="45" textAnchor="middle" className="fill-[hsl(340,75%,55%)]" fontSize="7" fontWeight="600">Ledger</text>

      {/* Arrow to specialists */}
      <line x1="188" y1="28" x2="220" y2="12" stroke="hsl(340 75% 55% / 0.4)" strokeWidth="1" />
      <line x1="188" y1="36" x2="220" y2="36" stroke="hsl(340 75% 55% / 0.4)" strokeWidth="1" />
      <line x1="188" y1="44" x2="220" y2="60" stroke="hsl(340 75% 55% / 0.4)" strokeWidth="1" />

      {/* Specialist nodes */}
      {[
        { y: 4, label: "Coder" },
        { y: 28, label: "Executor" },
        { y: 52, label: "Critic" },
      ].map((s) => (
        <g key={s.label}>
          <rect x="220" y={s.y} width="56" height="16" rx="4" fill="hsl(340 75% 55% / 0.1)" stroke="hsl(340 75% 55% / 0.35)" strokeWidth="1" />
          <text x="248" y={s.y + 11} textAnchor="middle" className="fill-[hsl(340,75%,55%,0.8)]" fontSize="7.5" fontWeight="500">{s.label}</text>
        </g>
      ))}

      {/* Feedback loop arrow (Ledger back to Manager) */}
      <path d="M 130 18 Q 130 4 80 4 Q 30 4 30 22" stroke="hsl(340 75% 55% / 0.35)" strokeWidth="1" strokeDasharray="4 2" fill="none" markerEnd="url(#arrowMag)" />
      <text x="80" y="12" textAnchor="middle" className="fill-[hsl(340,75%,55%,0.4)]" fontSize="5.5">re-plan</text>

      <defs>
        <marker id="arrowMag" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="hsl(340 75% 55% / 0.5)" />
        </marker>
      </defs>
    </svg>
  );
}

/* ── Pattern Cards ────────────────────────────────────────────── */

const PATTERNS = [
  {
    id: "sequential",
    title: "Sequential (Pipeline)",
    color: "hsl(201 90% 54%)",
    implemented: true,
    diagram: SequentialDiagram,
    description:
      "Linear pipeline where each agent runs in order, passing accumulated context forward. Best for workflows with clear dependencies between steps. Fails if any step blocks or produces bad output — no parallelism.",
    characteristics: [
      "Latency: O(n) serial",
      "Context accumulates per step",
      "Simple, predictable flow",
    ],
  },
  {
    id: "concurrent",
    title: "Concurrent (Fan-out / Fan-in)",
    color: "hsl(157 82% 40%)",
    implemented: true,
    diagram: ConcurrentDiagram,
    description:
      "All specialists execute concurrently, results are aggregated, then a coordinator synthesizes a final decision. Best for independent analyses that can run in parallel. Fails if one slow agent bottlenecks the merge.",
    characteristics: [
      "Latency: O(1) parallel",
      "All specialists run concurrently",
      "Deterministic aggregation step",
    ],
  },
  {
    id: "group_chat",
    title: "Group Chat (RoundTable)",
    color: "hsl(270 70% 60%)",
    implemented: false,
    diagram: GroupChatDiagram,
    description:
      "A manager selects which agent speaks next on a shared thread. Agents see each other's messages and can challenge or build on prior outputs. Best for debate, QA, and consensus-building. Fails with too many agents or unclear termination.",
    characteristics: [
      "Shared conversational thread",
      "Manager selects next speaker",
      "Natural debate / QA loop",
    ],
  },
  {
    id: "handoff",
    title: "Handoff (Triage / Routing)",
    color: "hsl(39 96% 57%)",
    implemented: true,
    diagram: HandoffDiagram,
    description:
      "Star topology where an LLM coordinator dynamically delegates to specialists based on the problem domain, then synthesizes results. Best for domain triage and specialist escalation. Fails if the router misclassifies the input.",
    characteristics: [
      "Dynamic agent selection",
      "Coordinator synthesizes results",
      "Flexible, adaptive routing",
    ],
  },
  {
    id: "magentic",
    title: "Magentic (Adaptive Planning)",
    color: "hsl(340 75% 55%)",
    implemented: false,
    diagram: MagenticDiagram,
    description:
      "A manager maintains a task ledger and dynamically assigns subtasks to specialist roles (Coder, Executor, Critic). The ledger is updated after each step, enabling re-planning. Best for open-ended problems with evolving subgoals and tool use.",
    characteristics: [
      "Task ledger tracks progress",
      "Dynamic re-planning loop",
      "Specialist roles (Coder / Executor / Critic)",
    ],
  },
];

const HEURISTIC_ROWS = [
  { need: "Known steps + dependencies", pattern: "Sequential" },
  { need: "Independent perspectives / parallelizable work", pattern: "Concurrent" },
  { need: "Debate / QA / consensus", pattern: "Group Chat" },
  { need: "Domain triage + specialist escalation", pattern: "Handoff" },
  { need: "Unknown plan + evolving subgoals + tools", pattern: "Magentic" },
];

function OrchestrationPatternsInner() {
  return (
    <div className="space-y-5">
      {/* Pattern cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {PATTERNS.map((pattern) => {
          const Diagram = pattern.diagram;
          return (
            <div
              key={pattern.id}
              className="flex flex-col rounded-xl border av-panel-muted p-4"
              style={{ borderColor: `${pattern.color}${pattern.implemented ? "25" : "15"}` }}
            >
              <div className="flex items-center gap-2">
                <h3
                  className="text-sm font-semibold"
                  style={{ color: pattern.color }}
                >
                  {pattern.title}
                </h3>
                {!pattern.implemented && (
                  <span
                    className="shrink-0 rounded-full border px-1.5 py-[1px] text-[8px] font-semibold"
                    style={{
                      color: `${pattern.color}`,
                      borderColor: `${pattern.color}40`,
                      backgroundColor: `${pattern.color}10`,
                    }}
                  >
                    Reference
                  </span>
                )}
              </div>

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

      {/* Selection Heuristic table */}
      <div className="rounded-xl border border-av-sky/15 av-panel-muted p-4">
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Selection Heuristic
        </h4>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-av-sky/10">
                <th className="pb-2 pr-4 text-left font-semibold text-muted-foreground">If you need...</th>
                <th className="pb-2 text-left font-semibold text-muted-foreground">Pattern</th>
              </tr>
            </thead>
            <tbody>
              {HEURISTIC_ROWS.map((row) => (
                <tr key={row.pattern} className="border-b border-av-sky/5 last:border-0">
                  <td className="py-1.5 pr-4 text-muted-foreground">{row.need}</td>
                  <td className="py-1.5 font-semibold text-foreground/90">{row.pattern}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Composition Guidance callout */}
      <div className="rounded-xl border border-av-sky/15 bg-av-sky/5 p-4">
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          <span className="font-semibold text-foreground/90">90% of the time: </span>
          Router (Handoff) &rarr; Sequential pipeline &rarr; Concurrent evaluation &rarr; Maker-Checker (Group Chat).
          Start simple — MS guidance warns against complex patterns when Sequential or Concurrent suffices.
        </p>
        <a
          href="https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns"
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-[10px] font-medium text-av-sky hover:underline"
        >
          Azure Architecture Center reference
          <ExternalLink className="h-2.5 w-2.5" />
        </a>
      </div>
    </div>
  );
}

export const OrchestrationPatterns = memo(OrchestrationPatternsInner);
