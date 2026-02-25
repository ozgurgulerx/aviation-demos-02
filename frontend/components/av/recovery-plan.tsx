"use client";

import { memo } from "react";
import { motion } from "framer-motion";
import { Trophy, Medal, Award, Clock } from "lucide-react";
import { useAviationStore } from "@/store/aviation-store";
import { ScoringRadar } from "./charts/scoring-radar";
import { cn } from "@/lib/utils";

const RANK_STYLES = [
  { borderColor: "hsl(var(--av-gold))", icon: Trophy, iconColor: "text-av-gold", scoreColor: "hsl(var(--av-gold))" },
  { borderColor: "hsl(var(--av-silver))", icon: Medal, iconColor: "text-av-silver", scoreColor: "hsl(var(--av-silver))" },
  { borderColor: "#cd7f32", icon: Award, iconColor: "text-orange-600", scoreColor: "#cd7f32" },
];

function RecoveryPlanViewInner() {
  const { recoveryPlan, recoveryOptions } = useAviationStore();
  const options = recoveryPlan?.options || recoveryOptions;

  if (options.length === 0 && !recoveryPlan) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <p className="text-xs">Recovery plan will appear after analysis completes</p>
      </div>
    );
  }

  const sortedOptions = [...options].sort((a, b) => a.rank - b.rank);

  return (
    <div className="av-scroll flex h-full gap-4 overflow-x-auto p-4">
      {/* Radar chart */}
      {sortedOptions.length > 0 && (
        <div className="w-[280px] shrink-0">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
            Multi-Objective Scoring
          </p>
          <ScoringRadar options={sortedOptions} />
        </div>
      )}

      {/* Options table */}
      <div className="flex-1 min-w-[300px]">
        <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-2">
          Ranked Options
        </p>
        <div className="space-y-1.5">
          {sortedOptions.map((opt, i) => {
            const rankStyle = i < 3 ? RANK_STYLES[i] : null;
            const RankIcon = rankStyle?.icon;
            return (
              <motion.div
                key={opt.optionId}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                className="flex items-center gap-3 rounded-md border border-border/45 bg-card/45 p-2 border-l-4"
                style={{
                  borderLeftColor: rankStyle?.borderColor || "hsl(var(--border))",
                }}
              >
                <div className="flex items-center gap-1.5 shrink-0 w-8">
                  {RankIcon && <RankIcon className={cn("w-3.5 h-3.5", rankStyle?.iconColor)} />}
                  <span className="text-xs font-bold text-muted-foreground">#{opt.rank}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-medium truncate">{opt.description}</p>
                  <div className="flex gap-2 mt-1">
                    {opt.scores && Object.entries(opt.scores).map(([key, val]) => (
                      <div key={key} className="flex items-center gap-1">
                        <div className="w-12 h-1 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${val}%`,
                              backgroundColor: rankStyle?.scoreColor || "hsl(var(--av-sky))",
                            }}
                          />
                        </div>
                        <span className="text-[8px] text-muted-foreground w-4">{Math.round(val)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <span
                    className="text-sm font-bold"
                    style={{ color: rankStyle?.scoreColor }}
                  >
                    {Math.round(opt.overallScore)}
                  </span>
                  <span className="text-[9px] text-muted-foreground block">score</span>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Timeline */}
        {recoveryPlan?.timeline && recoveryPlan.timeline.length > 0 && (
          <div className="mt-3">
            <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-2">
              Implementation Timeline
            </p>
            <div className="space-y-1">
              {recoveryPlan.timeline.map((entry, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  <Clock className="w-3 h-3 text-muted-foreground shrink-0" />
                  <span className="font-mono w-12 shrink-0 text-muted-foreground">{entry.time}</span>
                  <span className="flex-1 truncate">{entry.action}</span>
                  <span className="text-[10px] text-muted-foreground">{entry.agent}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export const RecoveryPlanView = memo(RecoveryPlanViewInner);
