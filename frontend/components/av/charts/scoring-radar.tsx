"use client";

import { ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Legend } from "recharts";
import type { RecoveryOption } from "@/types/aviation";

// Airline palette: Sky Blue, Green, Gold
const COLORS = ["#0ea5e9", "#10b981", "#f59e0b"];
const CRITERIA_LABELS: Record<string, string> = {
  delay_reduction: "Delay Reduction",
  crew_margin: "Crew Margin",
  safety_score: "Safety",
  cost_impact: "Cost Efficiency",
  passenger_impact: "Passenger Impact",
};

interface ScoringRadarProps {
  options: RecoveryOption[];
}

export function ScoringRadar({ options }: ScoringRadarProps) {
  const top3 = options.slice(0, 3);
  if (top3.length === 0) return null;

  const criteria = Object.keys(CRITERIA_LABELS);
  const data = criteria.map((key) => {
    const point: Record<string, string | number> = { criterion: CRITERIA_LABELS[key] };
    top3.forEach((opt, i) => {
      point[`option${i + 1}`] = opt.scores[key as keyof typeof opt.scores] || 0;
    });
    return point;
  });

  return (
    <ResponsiveContainer width="100%" height={220}>
      <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
        <PolarGrid stroke="hsl(var(--border))" />
        <PolarAngleAxis dataKey="criterion" tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} />
        <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 8 }} />
        {top3.map((opt, i) => (
          <Radar
            key={opt.optionId}
            name={`#${opt.rank} ${opt.description.slice(0, 20)}`}
            dataKey={`option${i + 1}`}
            stroke={COLORS[i]}
            fill={COLORS[i]}
            fillOpacity={0.15}
            strokeWidth={2}
          />
        ))}
        <Legend wrapperStyle={{ fontSize: 10 }} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
