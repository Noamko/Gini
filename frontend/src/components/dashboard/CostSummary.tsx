"use client";

import { DollarSign, Hash, Zap } from "lucide-react";
import type { CostSummary as CostData } from "@/stores/dashboardStore";

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 flex items-center gap-3">
      <div className="rounded-lg bg-zinc-800 p-2 text-zinc-400">{icon}</div>
      <div>
        <p className="text-xs text-zinc-500">{label}</p>
        <p className="text-lg font-semibold text-zinc-100">{value}</p>
      </div>
    </div>
  );
}

export function CostSummaryPanel({ costs }: { costs: CostData | null }) {
  if (!costs) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 h-20 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      <StatCard
        icon={<Hash size={18} />}
        label="Total Messages"
        value={costs.total_messages.toLocaleString()}
      />
      <StatCard
        icon={<Zap size={18} />}
        label="Total Tokens"
        value={costs.total_tokens.toLocaleString()}
      />
      <StatCard
        icon={<DollarSign size={18} />}
        label="Total Cost"
        value={`$${costs.total_cost.toFixed(4)}`}
      />
    </div>
  );
}
