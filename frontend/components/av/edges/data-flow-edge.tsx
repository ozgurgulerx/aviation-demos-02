"use client";

import { memo } from "react";
import { BaseEdge, getBezierPath, type EdgeProps } from "@xyflow/react";

function DataFlowEdgeInner({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps & { data?: { color?: string; animated?: boolean } }) {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const color = data?.color || "#0ea5e9";
  const isActive = data?.animated === true;

  return (
    <>
      {/* Glow background path when active */}
      {isActive && (
        <path
          d={edgePath}
          fill="none"
          stroke={color}
          strokeWidth={4}
          opacity={0.06}
          style={{ filter: "blur(3px)" }}
        />
      )}

      {/* Base path */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: isActive ? `${color}66` : `${color}22`,
          strokeWidth: isActive ? 2 : 1.5,
        }}
      />

      {/* Dashed stroke overlay with animated offset */}
      <path
        d={edgePath}
        fill="none"
        stroke={color}
        strokeWidth={isActive ? 2 : 1}
        strokeDasharray="6 4"
        opacity={isActive ? 0.8 : 0.24}
      >
        <animate
          attributeName="stroke-dashoffset"
          from="20"
          to="0"
          dur={isActive ? "1.2s" : "2s"}
          repeatCount="indefinite"
        />
      </path>

      {/* Single traveling particle */}
      {isActive && (
        <circle r="3" fill={color} opacity={0.7}>
          <animateMotion dur="1.8s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}
    </>
  );
}

export const DataFlowEdge = memo(DataFlowEdgeInner);
