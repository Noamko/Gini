"use client";

import { useEffect, useState } from "react";
import { LayoutDashboard, RefreshCw } from "lucide-react";
import { useDashboardStore } from "@/stores/dashboardStore";
import { AgentGrid } from "@/components/dashboard/AgentGrid";
import { CostSummaryPanel } from "@/components/dashboard/CostSummary";
import { EventStream } from "@/components/dashboard/EventStream";
import { CostBreakdownPanel } from "@/components/dashboard/CostBreakdown";

export default function DashboardPage() {
  const {
    agents,
    costs,
    events,
    costBreakdown,
    connected,
    loadAgents,
    loadCosts,
    loadEvents,
    loadCostBreakdown,
    connectWS,
    disconnectWS,
  } = useDashboardStore();

  const [breakdownBy, setBreakdownBy] = useState("model");

  useEffect(() => {
    loadAgents();
    loadCosts();
    loadEvents();
    loadCostBreakdown(breakdownBy);
    connectWS();
    return () => disconnectWS();
  }, [loadAgents, loadCosts, loadEvents, loadCostBreakdown, connectWS, disconnectWS, breakdownBy]);

  const refresh = () => {
    loadAgents();
    loadCosts();
    loadEvents();
    loadCostBreakdown(breakdownBy);
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto">
      <div className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <LayoutDashboard size={18} className="text-zinc-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Dashboard</h1>
          <span
            className={`ml-2 h-2 w-2 rounded-full ${
              connected ? "bg-emerald-500" : "bg-zinc-600"
            }`}
            title={connected ? "Live" : "Disconnected"}
          />
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-zinc-400 bg-zinc-800 rounded-lg hover:bg-zinc-700 transition-colors"
        >
          <RefreshCw size={12} />
          Refresh
        </button>
      </div>

      <div className="p-6 space-y-6 max-w-6xl mx-auto w-full">
        {/* Cost Summary */}
        <section>
          <h2 className="text-sm font-medium text-zinc-400 mb-3">Overview</h2>
          <CostSummaryPanel costs={costs} />
        </section>

        {/* Cost Breakdown */}
        <section>
          <CostBreakdownPanel
            breakdown={costBreakdown}
            groupBy={breakdownBy}
            onGroupByChange={(g) => setBreakdownBy(g)}
          />
        </section>

        {/* Agent Grid */}
        <section>
          <h2 className="text-sm font-medium text-zinc-400 mb-3">
            Agents ({agents.length})
          </h2>
          <AgentGrid agents={agents} />
        </section>

        {/* Event Stream */}
        <section>
          <EventStream events={events} />
        </section>
      </div>
    </div>
  );
}
