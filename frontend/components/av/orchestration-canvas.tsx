"use client";

import { useMemo, useEffect, useRef, useState, memo } from "react";
import {
  ReactFlow,
  Background,
  MiniMap,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useAviationStore } from "@/store/aviation-store";
import { TRACE_V2_ENABLED } from "@/lib/feature-flags";
import { CoordinatorNode } from "./nodes/coordinator-node";
import { AgentNode } from "./nodes/agent-node";
import { GhostNode } from "./nodes/ghost-node";
import { DataFlowEdge } from "./edges/data-flow-edge";
import { AlertTriangle, CheckCircle2, Database, Plane, Radar, Radio } from "lucide-react";

const nodeTypes = {
  coordinatorNode: CoordinatorNode,
  agentNode: AgentNode,
  ghostNode: GhostNode,
};

const edgeTypes = {
  dataFlow: DataFlowEdge,
};

// Updated node dimensions for rich cards
const NODE_SIZES: Record<string, { width: number; height: number }> = {
  coordinatorNode: { width: 116, height: 116 },
  agentNode: { width: 252, height: 182 },
  ghostNode: { width: 100, height: 40 },
};

const SPECIALIST_RADIUS = 320;
const GHOST_RADIUS = 460;
const CLUSTER_SPECIALIST_RADIUS = 90;
const CLUSTER_GHOST_RADIUS = 155;

/** Place nodes in radial rings around center (0,0) */
function getRadialLayout(nodes: Node[], edges: Edge[]) {
  const coordinators: Node[] = [];
  const specialists: Node[] = [];
  const ghosts: Node[] = [];

  for (const node of nodes) {
    if (node.type === "coordinatorNode") coordinators.push(node);
    else if (node.type === "ghostNode") ghosts.push(node);
    else specialists.push(node);
  }

  const layouted: Node[] = [];

  // Coordinator at center
  for (const coord of coordinators) {
    const size = NODE_SIZES.coordinatorNode;
    layouted.push({
      ...coord,
      position: { x: -size.width / 2, y: -size.height / 2 },
    });
  }

  // Specialists in inner ring
  specialists.forEach((node, i) => {
    const size = NODE_SIZES.agentNode;
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / specialists.length;
    layouted.push({
      ...node,
      position: {
        x: Math.cos(angle) * SPECIALIST_RADIUS - size.width / 2,
        y: Math.sin(angle) * SPECIALIST_RADIUS - size.height / 2,
      },
    });
  });

  // Ghosts in outer ring
  ghosts.forEach((node, i) => {
    const size = NODE_SIZES.ghostNode;
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(ghosts.length, 1);
    layouted.push({
      ...node,
      position: {
        x: Math.cos(angle) * GHOST_RADIUS - size.width / 2,
        y: Math.sin(angle) * GHOST_RADIUS - size.height / 2,
      },
    });
  });

  return { nodes: layouted, edges };
}

/** Initial assembling layout: everyone appears close to the orchestrator before orbiting out. */
function getClusterLayout(nodes: Node[], edges: Edge[]) {
  const coordinators: Node[] = [];
  const specialists: Node[] = [];
  const ghosts: Node[] = [];

  for (const node of nodes) {
    if (node.type === "coordinatorNode") coordinators.push(node);
    else if (node.type === "ghostNode") ghosts.push(node);
    else specialists.push(node);
  }

  const layouted: Node[] = [];

  for (const coord of coordinators) {
    const size = NODE_SIZES.coordinatorNode;
    layouted.push({
      ...coord,
      position: { x: -size.width / 2, y: -size.height / 2 },
      style: {
        ...(coord.style || {}),
        transition: "transform 950ms cubic-bezier(0.22, 1, 0.36, 1), opacity 300ms ease",
      },
    });
  }

  specialists.forEach((node, i) => {
    const size = NODE_SIZES.agentNode;
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(specialists.length, 1);
    layouted.push({
      ...node,
      position: {
        x: Math.cos(angle) * CLUSTER_SPECIALIST_RADIUS - size.width / 2,
        y: Math.sin(angle) * CLUSTER_SPECIALIST_RADIUS - size.height / 2,
      },
      style: {
        ...(node.style || {}),
        transition: "transform 950ms cubic-bezier(0.22, 1, 0.36, 1), opacity 300ms ease",
      },
    });
  });

  ghosts.forEach((node, i) => {
    const size = NODE_SIZES.ghostNode;
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(ghosts.length, 1);
    layouted.push({
      ...node,
      position: {
        x: Math.cos(angle) * CLUSTER_GHOST_RADIUS - size.width / 2,
        y: Math.sin(angle) * CLUSTER_GHOST_RADIUS - size.height / 2,
      },
      style: {
        ...(node.style || {}),
        transition: "transform 950ms cubic-bezier(0.22, 1, 0.36, 1), opacity 300ms ease",
      },
    });
  });

  return { nodes: layouted, edges };
}

function OrchestrationCanvasInner() {
  const agents = useAviationStore((s) => s.agents);
  const agentEdges = useAviationStore((s) => s.agentEdges);
  const scenario = useAviationStore((s) => s.scenario);
  const dataSources = useAviationStore((s) => s.dataSources);
  const runProgress = useAviationStore((s) => s.runProgress);
  const noUpdateWarning = useAviationStore((s) => s.noUpdateWarning);

  const agentList = Object.values(agents);
  const hasAgents = agentList.length > 0;
  const runningAgents = useMemo(
    () => agentList.filter((a) => a.status === "thinking" || a.status === "querying"),
    [agentList]
  );
  const completedAgents = useMemo(
    () => agentList.filter((a) => a.status === "done"),
    [agentList]
  );
  const prevTopologyRef = useRef<string>("");
  const assembleTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [isAssembling, setIsAssembling] = useState(false);

  // Stable serialization keys for memoization
  const agentKey = useMemo(
    () =>
      agentList
        .map(
          (a) =>
            `${a.id}:${a.status}:${a.evidence.length}:${a.activeQuery ?? ""}:${a.currentObjective ?? ""}:${a.confidence ?? ""}`
        )
        .join("|"),
    [agentList]
  );
  const edgeKey = useMemo(() => agentEdges.map((e) => e.id).join("|"), [agentEdges]);
  const topologyKey = useMemo(
    () =>
      agentList
        .map((a) => `${a.id}:${a.included ? 1 : 0}:${a.category}`)
        .sort()
        .join("|"),
    [agentList]
  );
  const azureQueryCount = useMemo(
    () =>
      Object.values(dataSources)
        .filter((source) => source.provider === "Azure")
        .reduce((sum, source) => sum + source.queryCount, 0),
    [dataSources]
  );
  const fabricQueryCount = useMemo(
    () =>
      Object.values(dataSources)
        .filter((source) => source.provider === "Fabric")
        .reduce((sum, source) => sum + source.queryCount, 0),
    [dataSources]
  );

  // Build React Flow nodes from agent state
  const { clusterNodes, radialNodes, initialEdges } = useMemo<{
    clusterNodes: Node[];
    radialNodes: Node[];
    initialEdges: Edge[];
  }>(() => {
    if (!hasAgents) return { clusterNodes: [], radialNodes: [], initialEdges: [] };

    const included = agentList.filter((a) => a.included);
    const excluded = agentList.filter((a) => !a.included);
    const coordinators = included.filter((a) => a.category === "coordinator");
    const specialists = included.filter((a) => a.category !== "coordinator");

    const rfNodes: Node[] = [];

    // Coordinator nodes
    coordinators.forEach((agent) => {
      rfNodes.push({
        id: agent.id,
        type: "coordinatorNode",
        position: { x: 0, y: 0 },
        data: {
          label: agent.name,
          icon: agent.icon,
          color: agent.color,
          status: agent.status,
          agentsCompleted: specialists.filter((a) => a.status === "done").length,
          agentsTotal: specialists.length,
          entryDelay: 0,
        },
      });
    });

    // Specialist nodes
    specialists.forEach((agent, index) => {
      rfNodes.push({
        id: agent.id,
        type: "agentNode",
        position: { x: 0, y: 0 },
        data: {
          label: agent.name,
          agentId: agent.id,
          icon: agent.icon,
          color: agent.color,
          status: agent.status,
          dataSources: agent.dataSources,
          evidenceCount: agent.evidence.length,
          traceCount: agent.traceCount ?? 0,
          activeQuery: agent.activeQuery,
          currentObjective: agent.currentObjective,
          activeQuerySummary: agent.activeQuerySummary,
          confidence: agent.confidence,
          lastEvidencePreview: agent.lastEvidencePreview,
          entryDelay: 0.08 + index * 0.05,
        },
      });
    });

    // Ghost nodes (excluded)
    excluded.slice(0, 6).forEach((agent) => {
      rfNodes.push({
        id: agent.id,
        type: "ghostNode",
        position: { x: 0, y: 0 },
        data: {
          label: agent.name,
          icon: agent.icon,
          color: agent.color,
        },
      });
    });

    // Build edges: coordinator -> each specialist
    const rfEdges: Edge[] = [];
    const coordId = coordinators[0]?.id;

    if (coordId) {
      specialists.forEach((agent) => {
        rfEdges.push({
          id: `e-${coordId}-${agent.id}`,
          source: coordId,
          target: agent.id,
          type: "dataFlow",
          data: {
            color: agent.color,
            animated: agent.status === "thinking" || agent.status === "querying",
          },
          animated: false,
        });
      });
    }

    // Handover edges from SSE events
    agentEdges.forEach((ae) => {
      if (!rfEdges.find((e) => e.source === ae.source && e.target === ae.target)) {
        rfEdges.push({
          id: ae.id,
          source: ae.source,
          target: ae.target,
          type: "dataFlow",
          data: { color: "#0ea5e9", animated: true },
          animated: true,
        });
      }
    });

    const { nodes: assembledNodes, edges: assembledEdges } = getClusterLayout(rfNodes, rfEdges);
    const { nodes: orbitNodes } = getRadialLayout(rfNodes, rfEdges);
    const orbitNodesWithTransition: Node[] = orbitNodes.map((node) => ({
      ...node,
      style: {
        ...(node.style || {}),
        transition: "transform 950ms cubic-bezier(0.22, 1, 0.36, 1), opacity 300ms ease",
      },
    }));
    return {
      clusterNodes: assembledNodes,
      radialNodes: orbitNodesWithTransition,
      initialEdges: assembledEdges,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentKey, edgeKey, hasAgents]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(radialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initialEdges);

  // Sync when agent state changes
  useEffect(() => {
    if (assembleTimerRef.current) {
      clearTimeout(assembleTimerRef.current);
      assembleTimerRef.current = null;
    }

    if (radialNodes.length > 0) {
      const topologyChanged = prevTopologyRef.current !== topologyKey;
      prevTopologyRef.current = topologyKey;
      setEdges(initialEdges);
      if (topologyChanged) {
        setIsAssembling(true);
        setNodes(clusterNodes);
        assembleTimerRef.current = setTimeout(() => {
          setNodes(radialNodes);
          setIsAssembling(false);
        }, 260);
      } else {
        setIsAssembling(false);
        setNodes(radialNodes);
      }
    } else {
      setIsAssembling(false);
      setNodes([]);
      setEdges([]);
    }

    return () => {
      if (assembleTimerRef.current) {
        clearTimeout(assembleTimerRef.current);
        assembleTimerRef.current = null;
      }
    };
  }, [clusterNodes, radialNodes, initialEdges, topologyKey, setNodes, setEdges]);

  useEffect(() => {
    if (!hasAgents) {
      prevTopologyRef.current = "";
      setIsAssembling(false);
      if (assembleTimerRef.current) {
        clearTimeout(assembleTimerRef.current);
        assembleTimerRef.current = null;
      }
    }
  }, [hasAgents]);

  if (!hasAgents) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-transparent text-muted-foreground">
        <div className="relative">
          <div className="absolute inset-0 h-52 w-52 -translate-x-1/2 -translate-y-1/2 rounded-full bg-av-sky/9 blur-3xl" />
          <Plane className="relative mb-4 h-12 w-12 opacity-20" />
        </div>
        <p className="relative text-sm font-semibold">Flight Ops Orchestration</p>
        <p className="relative mt-1 text-xs opacity-70">Launch a scenario to view real-time multi-agent execution</p>
      </div>
    );
  }

  return (
    <div className="h-full w-full relative">
      <div className="pointer-events-none absolute inset-0 z-[1] flex items-center justify-center">
        <div className="relative h-[560px] w-[560px]">
          <div className="absolute inset-[18%] rounded-full border border-av-gold/14 av-pulse-ring" />
          <div className="absolute inset-[7%] rounded-full border border-av-sky/18" />
          <div className="absolute inset-[29%] rounded-full border border-av-fabric/20" />
          <div className="absolute inset-0 rounded-full bg-[conic-gradient(from_0deg,transparent_0deg,hsl(var(--av-sky)/0.08)_70deg,transparent_130deg)] av-radar-sweep" />
          <div className="absolute inset-[44%] rounded-full bg-av-sky/16 blur-md" />
        </div>
      </div>

      {isAssembling && (
        <div className="pointer-events-none absolute inset-0 z-[15] flex items-center justify-center">
          <div className="rounded-full border border-av-sky/30 bg-av-midnight/75 px-3 py-1 text-[10px] font-semibold tracking-wider text-av-sky shadow-lg">
            FORMING AGENT RING...
          </div>
        </div>
      )}

      <div className="absolute left-3 top-3 z-20 flex items-center gap-2 text-[10px]">
        <div className="flex items-center gap-1 rounded-lg border border-av-azure/30 bg-av-azure/14 px-2 py-1 font-semibold text-av-azure">
          <Database className="w-3 h-3" />
          Azure queries {azureQueryCount}
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-av-fabric/30 bg-av-fabric/14 px-2 py-1 font-semibold text-av-fabric">
          <Database className="w-3 h-3" />
          Fabric queries {fabricQueryCount}
        </div>
        {scenario && (
          <div className="hidden items-center gap-1 rounded-lg border border-av-sky/25 bg-av-sky/12 px-2 py-1 font-semibold text-av-sky capitalize md:flex">
            <Radar className="w-3 h-3" />
            {scenario.replace(/_/g, " ")}
          </div>
        )}
      </div>

      {TRACE_V2_ENABLED && (
      <div className="absolute right-3 top-3 z-20 flex max-w-[40rem] flex-wrap items-center justify-end gap-2 text-[10px]">
        <div className="rounded-lg border border-av-sky/24 bg-av-sky/10 px-2 py-1 font-semibold text-av-sky">
          Progress {Math.round(runProgress.overallPct)}%
        </div>
        <div className="rounded-lg border border-av-green/24 bg-av-green/10 px-2 py-1 font-semibold text-av-green">
          Done {completedAgents.length}
        </div>
        <div className="rounded-lg border border-av-gold/24 bg-av-gold/10 px-2 py-1 font-semibold text-av-gold">
          Running {runningAgents.length}
        </div>
        {noUpdateWarning ? (
          <div className="rounded-lg border border-av-gold/30 bg-av-gold/15 px-2 py-1 font-semibold text-av-gold inline-flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" />
            Waiting for fresh traces
          </div>
        ) : (
          <div className="rounded-lg border border-av-green/24 bg-av-green/10 px-2 py-1 font-semibold text-av-green inline-flex items-center gap-1">
            <Radio className="w-3 h-3 animate-pulse" />
            Live telemetry
          </div>
        )}
      </div>
      )}

      {TRACE_V2_ENABLED && (
      <div className="absolute left-3 bottom-3 z-20 flex max-w-[75%] flex-wrap items-center gap-2">
        {runningAgents.length > 0 ? (
          runningAgents.slice(0, 4).map((agent) => (
            <div
              key={`running-${agent.id}`}
              className="rounded-full border border-av-sky/30 bg-av-midnight/78 px-2.5 py-1 text-[11px] text-av-sky inline-flex items-center gap-1.5"
            >
              <span className="h-1.5 w-1.5 rounded-full animate-pulse" style={{ backgroundColor: agent.color }} />
              <span className="font-semibold">{agent.name}</span>
              <span className="text-muted-foreground">{agent.currentStep || agent.status}</span>
            </div>
          ))
        ) : (
          <div className="rounded-full border border-av-green/30 bg-av-green/10 px-2.5 py-1 text-[11px] font-semibold text-av-green inline-flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" />
            No active agents. Waiting or completed.
          </div>
        )}
      </div>
      )}

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.3}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        className="relative z-10 bg-transparent"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={24}
          size={1}
          color="hsl(var(--av-sky) / 0.13)"
        />
        <MiniMap
          nodeStrokeWidth={2}
          className="!rounded-lg !border-av-sky/25 !bg-av-midnight/88 shadow-[0_8px_24px_rgba(0,0,0,0.35)]"
          maskColor="hsl(var(--av-navy) / 0.7)"
          style={{ width: 120, height: 80 }}
        />
        <Controls
          className="!rounded-lg !border-av-sky/30 !bg-av-midnight/90 !shadow-md [&>button]:!border-av-sky/25 [&>button]:!bg-av-midnight [&>button]:!text-foreground"
          showInteractive={false}
        />
      </ReactFlow>
    </div>
  );
}

export const OrchestrationCanvas = memo(OrchestrationCanvasInner);
