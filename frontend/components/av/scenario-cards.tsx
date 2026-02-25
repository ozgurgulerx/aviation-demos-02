"use client";

import { motion } from "framer-motion";
import { CloudLightning, Wrench, Navigation, Users } from "lucide-react";
import type { ScenarioCard } from "@/types/aviation";

const SCENARIOS: ScenarioCard[] = [
  {
    id: "hub_disruption",
    title: "Hub Disruption Recovery",
    subtitle: "ORD thunderstorm, 47 flights affected",
    icon: "CloudLightning",
    color: "#ef4444",
    prompt: "Severe thunderstorm at Chicago O'Hare (ORD) has caused a ground stop. 47 flights are delayed or cancelled, affecting approximately 6,800 passengers. 12 aircraft are grounded, 3 runways closed. Develop a recovery plan to minimize total delay and passenger impact while maintaining crew legality and safety compliance.",
  },
  {
    id: "predictive_maintenance",
    title: "Predictive Maintenance",
    subtitle: "737 fleet MEL trend alert",
    icon: "Wrench",
    color: "#f59e0b",
    prompt: "The Boeing 737-800 fleet is showing a trending increase in MEL deferrals for JASC code 7200 (engine) items over the past 30 days. Three aircraft (N738AA, N739AA, N741AA) have repeat deferrals. Analyze the MEL trends, search for similar historical incidents, and recommend whether to escalate inspections or adjust dispatch procedures.",
  },
  {
    id: "diversion",
    title: "Diversion Decision",
    subtitle: "AA1847 fuel critical near DTW",
    icon: "Navigation",
    color: "#14b8a6",
    prompt: "Flight AA1847 (B737-800, N735AA) en route from JFK to ORD is encountering severe weather at the destination. Current position is 80nm east of Detroit (DTW). Fuel remaining is 90 minutes. ORD is reporting visibility below minimums with thunderstorms. Evaluate diversion alternates and recommend the best course of action.",
  },
  {
    id: "crew_fatigue",
    title: "Crew Fatigue Assessment",
    subtitle: "Red-eye crew approaching limits",
    icon: "Users",
    color: "#0ea5e9",
    prompt: "The crew operating red-eye flights from LAX hub are showing elevated fatigue indicators. Captain J. Smith (crew ID CR-4421) has accumulated 11.5 hours of duty time with a red-eye departure at 23:45. Three first officers on the same rotation are approaching FAR 117 cumulative duty limits. Assess fatigue risk and recommend mitigation measures.",
  },
];

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  CloudLightning,
  Wrench,
  Navigation,
  Users,
};

interface ScenarioCardsProps {
  onSelect: (prompt: string) => void;
}

export function ScenarioCards({ onSelect }: ScenarioCardsProps) {
  return (
    <div className="space-y-2">
      <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider px-1">
        Demo Scenarios
      </p>
      {SCENARIOS.map((scenario, i) => {
        const Icon = ICON_MAP[scenario.icon] || CloudLightning;
        return (
          <motion.button
            key={scenario.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            onClick={() => onSelect(scenario.prompt)}
            className="group w-full rounded-lg border border-av-sky/16 bg-av-surface/72 p-3 text-left transition-all hover:border-av-sky/35 hover:bg-av-surface/90"
            style={{ borderLeftWidth: 3, borderLeftColor: `${scenario.color}40` }}
            whileHover={{ borderLeftColor: scenario.color }}
          >
            <div className="flex items-start gap-2.5">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
                style={{ backgroundColor: `${scenario.color}15` }}
              >
                <span style={{ color: scenario.color }}><Icon className="w-4 h-4" /></span>
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold truncate group-hover:text-av-sky transition-colors">
                  {scenario.title}
                </p>
                <p className="text-[11px] text-muted-foreground truncate">
                  {scenario.subtitle}
                </p>
              </div>
            </div>
          </motion.button>
        );
      })}
    </div>
  );
}
