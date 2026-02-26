"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Radar } from "lucide-react";

interface GhostData {
  label: string;
  icon: string;
  color: string;
  [key: string]: unknown;
}

function GhostNodeInner({ data }: NodeProps & { data: GhostData }) {
  return (
    <div className="w-[100px] rounded-lg border border-dashed border-border/20 bg-card/20 p-2 opacity-30">
      <div className="flex items-center gap-1.5">
        <div className="w-5 h-5 rounded flex items-center justify-center bg-muted/30">
          <Radar className="w-3 h-3 text-muted-foreground/50" />
        </div>
        <div className="min-w-0">
          <p className="text-[9px] font-medium truncate text-muted-foreground/60">{data.label}</p>
          <p className="text-[8px] text-muted-foreground/40">Excluded</p>
        </div>
      </div>

      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0 !w-1 !h-1" />
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-1 !h-1" />
    </div>
  );
}

export const GhostNode = memo(GhostNodeInner);
