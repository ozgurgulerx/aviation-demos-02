"use client";

import * as Tabs from "@radix-ui/react-tabs";
import { ChevronUp, ChevronDown, Clock, FileText, Database, Activity, Waves } from "lucide-react";
import { useAviationStore } from "@/store/aviation-store";
import { cn } from "@/lib/utils";

interface BottomDrawerProps {
  panels: {
    activity: React.ReactNode;
    timeline: React.ReactNode;
    plan: React.ReactNode;
    sources: React.ReactNode;
  };
}

export function BottomDrawer({ panels }: BottomDrawerProps) {
  const {
    bottomDrawerTab,
    setBottomDrawerTab,
    bottomDrawerOpen,
    setBottomDrawerOpen,
    events,
    recoveryPlan,
    dataSources,
  } = useAviationStore();

  const activeDataSources = Object.values(dataSources).filter((source) => source.queryCount > 0).length;

  const tabs = [
    { id: "activity" as const, label: "Agent Traces", icon: Activity, count: events.length },
    { id: "timeline" as const, label: "Event Timeline", icon: Clock, count: events.length },
    { id: "plan" as const, label: "Recovery Plan", icon: FileText, count: recoveryPlan ? 1 : 0 },
    { id: "sources" as const, label: "Datastores", icon: Database, count: activeDataSources },
  ];

  return (
    <Tabs.Root
      value={bottomDrawerTab}
      onValueChange={(v) => setBottomDrawerTab(v as typeof bottomDrawerTab)}
      className="flex h-full flex-col bg-gradient-to-b from-av-surface/74 to-av-midnight/72"
    >
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-av-sky/20 bg-av-midnight/78 px-2.5">
        <Tabs.List className="flex gap-1.5">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <Tabs.Trigger
                key={tab.id}
                value={tab.id}
                className={cn(
                  "flex items-center gap-1.5 rounded-md border border-transparent px-2.5 py-1 text-[11px] font-semibold tracking-wide transition-colors",
                  "hover:bg-accent/60 data-[state=active]:border-av-sky/30 data-[state=active]:bg-av-sky/14 data-[state=active]:text-av-sky",
                  "text-muted-foreground"
                )}
              >
                <Icon className="w-3 h-3" />
                {tab.label}
                {tab.count > 0 && (
                  <span className="rounded-full bg-muted-foreground/20 px-1.5 text-[9px] font-mono">
                    {tab.count}
                  </span>
                )}
              </Tabs.Trigger>
            );
          })}
        </Tabs.List>

        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-1 text-[10px] text-muted-foreground md:flex">
            <Waves className="w-3 h-3 text-av-fabric" />
            SSE Trace Bus
          </span>
          <button
            onClick={() => setBottomDrawerOpen(!bottomDrawerOpen)}
            className="rounded p-1 transition hover:bg-accent/60"
            aria-label={bottomDrawerOpen ? "Collapse drawer" : "Expand drawer"}
          >
            {bottomDrawerOpen ? (
              <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
            ) : (
              <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>

      {bottomDrawerOpen && (
        <div className="min-h-0 flex-1 overflow-hidden">
          <Tabs.Content value="activity" className="av-scroll h-full overflow-y-auto">
            {panels.activity}
          </Tabs.Content>
          <Tabs.Content value="timeline" className="av-scroll h-full overflow-y-auto">
            {panels.timeline}
          </Tabs.Content>
          <Tabs.Content value="plan" className="av-scroll h-full overflow-y-auto">
            {panels.plan}
          </Tabs.Content>
          <Tabs.Content value="sources" className="av-scroll h-full overflow-y-auto">
            {panels.sources}
          </Tabs.Content>
        </div>
      )}
    </Tabs.Root>
  );
}
