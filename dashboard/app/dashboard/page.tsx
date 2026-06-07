"use client";

import { AgentGrid } from "../components/AgentGrid";
import { AuditStream } from "../components/AuditStream";
import { DecisionFeed } from "../components/DecisionFeed";
import { DemoControls } from "../components/DemoControls";
import { EventTicker } from "../components/EventTicker";
import { KillSwitch } from "../components/KillSwitch";
import { McpCapabilitiesPanel } from "../components/McpCapabilitiesPanel";
import { OfflineBanner } from "../components/OfflineBanner";
import { PositionPanel } from "../components/PositionPanel";
import { StrategyEditor } from "../components/StrategyEditor";
import { ProofOfExecution } from "@/components/ProofOfExecution";
import { DemoModeTrustBadge, WorkbenchHeader } from "@/components/sentinel";
import { useSentinelWebSocket } from "@/hooks/use-sentinel-ws";

export default function DashboardPage() {
  useSentinelWebSocket();

  return (
    <div className="workbench-root min-h-screen">
      <OfflineBanner />
      <WorkbenchHeader />
      <main className="workbench-main mx-auto w-full py-8 md:py-10">
        <div className="mb-6 md:mb-8">
          <ProofOfExecution />
        </div>
        <div className="workbench-grid grid gap-8 lg:grid-cols-[minmax(260px,0.82fr)_minmax(0,2.35fr)_minmax(260px,0.88fr)]">
          <aside className="workbench-rail flex flex-col lg:sticky lg:top-[4.5rem] lg:max-h-[calc(100vh-5.5rem)] lg:overflow-y-auto lg:self-start">
            <KillSwitch />
            <StrategyEditor />
            <McpCapabilitiesPanel />
            <PositionPanel />
          </aside>

          <div className="workbench-center flex min-h-0 min-w-0 flex-col">
            <AgentGrid />
            <DecisionFeed />
          </div>

          <aside className="workbench-rail flex min-h-0 flex-col lg:sticky lg:top-[4.5rem] lg:max-h-[calc(100vh-5.5rem)] lg:overflow-y-auto lg:self-start">
            <DemoControls />
            <AuditStream />
            <EventTicker />
          </aside>
        </div>
      </main>
      <DemoModeTrustBadge />
    </div>
  );
}
