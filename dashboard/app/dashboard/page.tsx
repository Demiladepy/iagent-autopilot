"use client";

import { AgentGrid } from "../components/AgentGrid";
import { AuditStream } from "../components/AuditStream";
import { DecisionFeed } from "../components/DecisionFeed";
import { DemoControls } from "../components/DemoControls";
import { EventTicker } from "../components/EventTicker";
import { KillSwitch } from "../components/KillSwitch";
import { OfflineBanner } from "../components/OfflineBanner";
import { PositionPanel } from "../components/PositionPanel";
import { StrategyEditor } from "../components/StrategyEditor";
import { WorkbenchHeader } from "@/components/sentinel";
import { useSentinelWebSocket } from "@/hooks/use-sentinel-ws";

export default function DashboardPage() {
  useSentinelWebSocket();

  return (
    <div className="workbench-root min-h-screen">
      <OfflineBanner />
      <WorkbenchHeader />
      <main className="mx-auto max-w-[1600px] px-4 py-6 md:px-6 md:py-8">
        <div className="grid gap-6 lg:grid-cols-[minmax(280px,300px)_minmax(0,1fr)_minmax(280px,320px)] lg:gap-8">
          <aside className="flex flex-col gap-5 lg:sticky lg:top-[4.5rem] lg:max-h-[calc(100vh-5.5rem)] lg:overflow-y-auto lg:self-start">
            <KillSwitch />
            <StrategyEditor />
            <PositionPanel />
          </aside>

          <div className="flex min-h-0 min-w-0 flex-col gap-6">
            <AgentGrid />
            <DecisionFeed />
          </div>

          <aside className="flex min-h-0 flex-col gap-5 lg:sticky lg:top-[4.5rem] lg:max-h-[calc(100vh-5.5rem)] lg:overflow-y-auto lg:self-start">
            <DemoControls />
            <AuditStream />
            <EventTicker />
          </aside>
        </div>
      </main>
    </div>
  );
}
