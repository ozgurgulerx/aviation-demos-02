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
      {/* SVG filter for particle glow */}
      <defs>
        <filter id={`glow-${id}`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {/* Glow background path when active */}
      {isActive && (
        <path
          d={edgePath}
          fill="none"
          stroke={color}
          strokeWidth={6}
          opacity={0.1}
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
          dur={isActive ? "0.6s" : "2s"}
          repeatCount="indefinite"
        />
        {isActive && (
          <animate
            attributeName="opacity"
            values="0.45;0.9;0.45"
            dur="1.2s"
            repeatCount="indefinite"
          />
        )}
      </path>

      {/* Staggered particles — data stream effect */}
      {isActive && (
        <>
          <circle r="3.5" fill={color} opacity={0.9} filter={`url(#glow-${id})`}>
            <animateMotion dur="1.4s" repeatCount="indefinite" path={edgePath} />
          </circle>
          <circle r="2.5" fill={color} opacity={0.6} filter={`url(#glow-${id})`}>
            <animateMotion dur="1.4s" repeatCount="indefinite" path={edgePath} begin="0.7s" />
          </circle>
          <circle r="1.5" fill={color} opacity={0.35}>
            <animateMotion dur="1.4s" repeatCount="indefinite" path={edgePath} begin="1.4s" />
          </circle>
        </>
      )}
    </>
  );
}

export const DataFlowEdge = memo(DataFlowEdgeInner);
