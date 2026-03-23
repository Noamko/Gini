"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Activity, Clock, Coins, Zap, ChevronRight } from "lucide-react";
import { api } from "@/lib/api-client";

interface TraceSummary {
  trace_id: string;
  conversation_id: string | null;
  agent_name: string | null;
  step_count: number;
  total_duration_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  started_at: string;
  step_types: string[];
}

const STEP_TYPE_COLORS: Record<string, string> = {
  llm_call: "bg-blue-500/20 text-blue-400",
  tool_call: "bg-amber-500/20 text-amber-400",
  delegation: "bg-purple-500/20 text-purple-400",
};

export default function TracesPage() {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [costSummary, setCostSummary] = useState<any>(null);
  const [breakdown, setBreakdown] = useState<any[]>([]);
  const [breakdownBy, setBreakdownBy] = useState("model");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [tracesData, costs, bd] = await Promise.all([
        api.traces.list({ limit: 50 }),
        api.traces.costs(),
        api.traces.breakdown(breakdownBy),
      ]);
      setTraces(tracesData.items);
      setTotal(tracesData.total);
      setCostSummary(costs);
      setBreakdown(bd);
    } catch {
      // ignore
    }
    setLoading(false);
  }, [breakdownBy]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto">
      <div className="border-b border-zinc-800 px-6 py-4 flex items-center gap-2">
        <Activity size={18} className="text-zinc-400" />
        <h1 className="text-lg font-semibold text-zinc-100">Execution Traces</h1>
        <span className="text-xs text-zinc-500 ml-2">{total} traces</span>
      </div>

      <div className="p-6 space-y-6 max-w-6xl mx-auto w-full">
        {/* Cost Overview */}
        {costSummary && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Total Traces" value={String(costSummary.total_traces)} icon={<Activity size={16} />} />
            <StatCard label="Total Steps" value={String(costSummary.total_steps)} icon={<Zap size={16} />} />
            <StatCard label="Total Tokens" value={(costSummary.total_input_tokens + costSummary.total_output_tokens).toLocaleString()} icon={<Clock size={16} />} />
            <StatCard label="Total Cost" value={`$${costSummary.total_cost.toFixed(4)}`} icon={<Coins size={16} />} />
          </div>
        )}

        {/* Cost Breakdown */}
        {breakdown.length > 0 && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-zinc-300">Cost Breakdown</h3>
              <div className="flex gap-1">
                {["model", "agent", "step_type"].map((g) => (
                  <button
                    key={g}
                    onClick={() => setBreakdownBy(g)}
                    className={`px-2 py-1 text-[11px] rounded ${
                      breakdownBy === g
                        ? "bg-zinc-700 text-zinc-200"
                        : "text-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    {g}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-1">
              {breakdown.map((row, i) => (
                <div key={i} className="flex items-center gap-3 text-xs py-1.5">
                  <span className="text-zinc-300 font-mono w-48 truncate">{row.group || "unknown"}</span>
                  <span className="text-zinc-500">{row.count} calls</span>
                  <span className="text-zinc-500">{(row.input_tokens + row.output_tokens).toLocaleString()} tokens</span>
                  <span className="text-emerald-400 ml-auto font-medium">${row.cost_usd.toFixed(4)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Trace List */}
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-zinc-400">Recent Traces</h3>
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 h-20 animate-pulse" />
              ))}
            </div>
          ) : traces.length === 0 ? (
            <div className="text-center py-16 text-zinc-500 text-sm">
              No traces yet. Start a conversation to generate traces.
            </div>
          ) : (
            traces.map((t) => (
              <Link
                key={t.trace_id}
                href={`/traces/${t.trace_id}`}
                className="block rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 hover:border-zinc-700 transition-colors group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono text-zinc-300">
                          {t.trace_id.slice(0, 8)}
                        </span>
                        {t.agent_name && (
                          <span className="text-xs text-zinc-500">{t.agent_name}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        {t.step_types.map((st) => (
                          <span
                            key={st}
                            className={`text-[10px] px-1.5 py-0.5 rounded ${
                              STEP_TYPE_COLORS[st] || "bg-zinc-800 text-zinc-400"
                            }`}
                          >
                            {st}
                          </span>
                        ))}
                        <span className="text-[11px] text-zinc-600">
                          {t.step_count} steps
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-zinc-500">
                    <span>{(t.total_input_tokens + t.total_output_tokens).toLocaleString()} tok</span>
                    <span className="text-emerald-400">${t.total_cost_usd.toFixed(4)}</span>
                    <span>{(t.total_duration_ms / 1000).toFixed(1)}s</span>
                    <span>{new Date(t.started_at).toLocaleTimeString()}</span>
                    <ChevronRight size={14} className="text-zinc-600 group-hover:text-zinc-400" />
                  </div>
                </div>
              </Link>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-3 flex items-center gap-3">
      <div className="rounded-lg bg-zinc-800 p-2 text-zinc-400">{icon}</div>
      <div>
        <p className="text-[11px] text-zinc-500">{label}</p>
        <p className="text-sm font-semibold text-zinc-100">{value}</p>
      </div>
    </div>
  );
}
