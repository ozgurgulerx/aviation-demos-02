"use client";

import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { HeaderBar } from "@/components/av/header-bar";
import { ChatSidebar } from "@/components/av/chat-sidebar";
import { OrchestrationCanvas } from "@/components/av/orchestration-canvas";
import { BottomDrawer } from "@/components/av/bottom-drawer";
import { AgentActivityFeed } from "@/components/av/agent-activity-feed";
import { EventTimeline } from "@/components/av/event-timeline";
import { RecoveryPlanView } from "@/components/av/recovery-plan";
import { DataSourceActivityView } from "@/components/av/data-source-activity";
import { AgentDetailPanel } from "@/components/av/agent-detail-panel";
import { ErrorBoundary } from "@/components/av/error-boundary";

export default function Home() {
  return (
    <div className="flex h-screen flex-col bg-transparent">
      <HeaderBar />

      <div className="relative flex-1 overflow-hidden px-3 pb-3 md:px-4 md:pb-4">
        <div className="pointer-events-none absolute inset-0 av-grid opacity-30" />
        <div className="pointer-events-none absolute -top-20 left-1/2 h-52 w-[58rem] -translate-x-1/2 rounded-full bg-av-sky/10 blur-3xl" />
        <div className="relative h-full overflow-hidden rounded-[1.35rem] av-shell">
          <PanelGroup direction="horizontal">
            <Panel defaultSize={23} minSize={4} maxSize={35}>
              <ChatSidebar />
            </Panel>

            <PanelResizeHandle className="w-px bg-av-sky/14 hover:bg-av-sky/45 transition-colors" />

            <Panel defaultSize={77}>
              <PanelGroup direction="vertical">
                <Panel defaultSize={70} minSize={30}>
                  <ErrorBoundary fallbackMessage="Failed to render orchestration canvas">
                    <OrchestrationCanvas />
                  </ErrorBoundary>
                </Panel>

                <PanelResizeHandle className="h-px bg-av-sky/14 hover:bg-av-sky/45 transition-colors" />

                <Panel defaultSize={30} minSize={8} maxSize={62}>
                  <BottomDrawer
                    children={{
                      activity: <AgentActivityFeed />,
                      timeline: <EventTimeline />,
                      plan: <RecoveryPlanView />,
                      sources: <DataSourceActivityView />,
                    }}
                  />
                </Panel>
              </PanelGroup>
            </Panel>
          </PanelGroup>
        </div>

        <ErrorBoundary fallbackMessage="Failed to load agent details">
          <AgentDetailPanel />
        </ErrorBoundary>
      </div>
    </div>
  );
}
