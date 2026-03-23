"use client";

import { Coins } from "lucide-react";
import type { CostBreakdownRow } from "@/stores/dashboardStore";

interface Props {
  breakdown: CostBreakdownRow[];
  groupBy: string;
  onGroupByChange: (g: string) => void;
}

export function CostBreakdownPanel({ breakdown, groupBy, onGroupByChange }: Props) {
  if (breakdown.length === 0) {
    return null;
  }

  const maxCost = Math.max(...breakdown.map((r) => r.cost_usd), 0.0001);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Coins size={14} className="text-zinc-400" />
          <h3 className="text-sm font-medium text-zinc-300">Cost Breakdown</h3>
        </div>
        <div className="flex gap-1">
          {["model", "agent", "step_type"].map((g) => (
            <button
              key={g}
              onClick={() => onGroupByChange(g)}
              className={`px-2 py-1 text-[11px] rounded transition-colors ${
                groupBy === g
                  ? "bg-zinc-700 text-zinc-200"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {g}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-2">
        {breakdown.map((row, i) => (
          <div key={i} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-300 font-mono truncate max-w-[200px]">
                {row.group || "unknown"}
              </span>
              <div className="flex items-center gap-3 text-zinc-500">
                <span>{row.count} calls</span>
                <span>{(row.input_tokens + row.output_tokens).toLocaleString()} tok</span>
                <span className="text-emerald-400 font-medium w-20 text-right">
                  ${row.cost_usd.toFixed(4)}
                </span>
              </div>
            </div>
            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500/60 rounded-full transition-all"
                style={{ width: `${(row.cost_usd / maxCost) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
