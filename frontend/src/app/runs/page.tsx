"use client";

import { useEffect, useState, useCallback } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { api } from "@/lib/api-client";
import {
  Play,
  Pause,
  Square,
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  Bot,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  RotateCcw,
} from "lucide-react";

interface AgentRun {
  id: string;
  agent_id: string;
  agent_name: string;
  status: "pending" | "running" | "paused" | "done" | "failed";
  instructions: string | null;
  result: string | null;
  error: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_ms: number;
  steps: any[];
  created_at: string;
  updated_at: string;
}

const STATUS_CONFIG = {
  pending: { icon: Clock, color: "text-zinc-400", bg: "bg-zinc-800", label: "Pending" },
  running: { icon: Loader2, color: "text-blue-400", bg: "bg-blue-950/30", label: "Running" },
  paused: { icon: Pause, color: "text-amber-400", bg: "bg-amber-950/30", label: "Paused" },
  done: { icon: CheckCircle, color: "text-emerald-400", bg: "bg-emerald-950/30", label: "Done" },
  failed: { icon: XCircle, color: "text-red-400", bg: "bg-red-950/30", label: "Failed" },
};

function StatusBadge({ status }: { status: AgentRun["status"] }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${cfg.color} ${cfg.bg} border border-current/20`}>
      <Icon size={12} className={status === "running" ? "animate-spin" : ""} />
      {cfg.label}
    </span>
  );
}

function RunCard({ run, expanded, onToggle, onRetry, onStop, onPause, onResume }: {
  run: AgentRun; expanded: boolean; onToggle: () => void;
  onRetry: () => void; onStop: () => void; onPause: () => void; onResume: () => void;
}) {
  const created = new Date(run.created_at);
  const timeAgo = getTimeAgo(created);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-zinc-800/50 transition-colors text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-violet-600/20 flex items-center justify-center shrink-0">
            <Bot size={16} className="text-violet-400" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{run.agent_name}</span>
              <StatusBadge status={run.status} />
            </div>
            <p className="text-xs text-zinc-500 truncate">
              {run.instructions || "No instructions"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-3">
          <div className="text-right text-[11px] text-zinc-500">
            <div>{timeAgo}</div>
            {run.duration_ms > 0 && <div>{(run.duration_ms / 1000).toFixed(1)}s</div>}
          </div>
          {expanded ? <ChevronUp size={14} className="text-zinc-500" /> : <ChevronDown size={14} className="text-zinc-500" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-zinc-800 px-4 py-3 space-y-3">
          {/* Stats */}
          <div className="flex gap-4 text-xs text-zinc-500">
            <span>{run.input_tokens + run.output_tokens} tokens</span>
            <span>${run.cost_usd.toFixed(4)}</span>
            <span>{run.steps.length} steps</span>
          </div>

          {/* Result */}
          {run.result && (
            <div>
              <p className="text-[11px] text-zinc-500 mb-1">Result</p>
              <pre className="text-xs text-zinc-300 bg-zinc-950 rounded-lg p-3 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap">
                {run.result}
              </pre>
            </div>
          )}

          {/* Error */}
          {run.error && (
            <div>
              <p className="text-[11px] text-red-400 mb-1">Error</p>
              <pre className="text-xs text-red-300 bg-red-950/20 rounded-lg p-3 overflow-x-auto">
                {run.error}
              </pre>
            </div>
          )}

          {/* Run controls */}
          <div className="flex gap-2">
            {run.status === "running" && (
              <>
                <button onClick={onPause}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-xs text-white transition-colors">
                  <Pause size={12} /> Pause
                </button>
                <button onClick={onStop}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-xs text-white transition-colors">
                  <Square size={12} /> Stop
                </button>
              </>
            )}
            {run.status === "paused" && (
              <>
                <button onClick={onResume}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs text-white transition-colors">
                  <Play size={12} /> Resume
                </button>
                <button onClick={onStop}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-xs text-white transition-colors">
                  <Square size={12} /> Stop
                </button>
              </>
            )}
            {run.status === "failed" && (
              <button onClick={onRetry}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-xs text-white transition-colors">
                <RotateCcw size={12} /> Retry
              </button>
            )}
          </div>

          {/* Steps */}
          {run.steps.length > 0 && (
            <div>
              <p className="text-[11px] text-zinc-500 mb-1">Steps</p>
              <div className="space-y-1">
                {run.steps.map((step, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className={`w-2 h-2 rounded-full ${
                      step.type === "llm_call" ? "bg-blue-400" :
                      step.success === false ? "bg-red-400" : "bg-emerald-400"
                    }`} />
                    <span className="text-zinc-400">
                      {step.type === "llm_call"
                        ? `LLM round ${step.round} → ${step.tool_calls} tool calls`
                        : `${step.tool} → ${step.success ? "ok" : "failed"}`
                      }
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function getTimeAgo(date: Date): string {
  const s = Math.floor((Date.now() - date.getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function RunsPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("");

  const loadRuns = useCallback(async () => {
    try {
      const params = filter ? { status: filter } : undefined;
      const data = await api.runs.list(params);
      setRuns(data.items);
    } catch {}
    setLoading(false);
  }, [filter]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  // Auto-refresh if any runs are pending/running
  useEffect(() => {
    const hasActive = runs.some((r) => r.status === "pending" || r.status === "running");
    if (!hasActive) return;
    const timer = setInterval(loadRuns, 2000);
    return () => clearInterval(timer);
  }, [runs, loadRuns]);

  const counts = {
    all: runs.length,
    running: runs.filter((r) => r.status === "running" || r.status === "pending").length,
    done: runs.filter((r) => r.status === "done").length,
    failed: runs.filter((r) => r.status === "failed").length,
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-3 pt-14 md:p-6 md:pt-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Runs</h1>
              <p className="text-sm text-zinc-500 mt-1">Background agent executions</p>
            </div>
            <button
              onClick={loadRuns}
              className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-400 transition-colors"
            >
              <RefreshCw size={16} />
            </button>
          </div>

          {/* Filters */}
          <div className="flex gap-2">
            {[
              { value: "", label: "All", count: counts.all },
              { value: "running", label: "Running", count: counts.running },
              { value: "done", label: "Done", count: counts.done },
              { value: "failed", label: "Failed", count: counts.failed },
            ].map((f) => (
              <button
                key={f.value}
                onClick={() => setFilter(f.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  filter === f.value
                    ? "bg-violet-600 text-white"
                    : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                }`}
              >
                {f.label} ({f.count})
              </button>
            ))}
          </div>

          {/* Run list */}
          {loading ? (
            <p className="text-sm text-zinc-500">Loading runs...</p>
          ) : runs.length === 0 ? (
            <div className="text-center py-12 text-zinc-500">
              <Play size={32} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm">No runs yet. Start one from the Agents page.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {runs.map((run) => (
                <RunCard
                  key={run.id}
                  run={run}
                  expanded={expandedId === run.id}
                  onToggle={() => setExpandedId(expandedId === run.id ? null : run.id)}
                  onRetry={async () => { await api.runs.retry(run.id); loadRuns(); }}
                  onStop={async () => { await api.runs.stop(run.id); loadRuns(); }}
                  onPause={async () => { await api.runs.pause(run.id); loadRuns(); }}
                  onResume={async () => { await api.runs.resume(run.id); loadRuns(); }}
                />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
