"use client";

import { Bot, Cpu, Loader2, ArrowRightLeft, CheckCircle2, AlertCircle, Circle } from "lucide-react";
import type { AgentState } from "@/stores/dashboardStore";

const STATE_CONFIG: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  idle: { color: "bg-zinc-500", icon: <Circle size={12} />, label: "Idle" },
  thinking: { color: "bg-blue-500", icon: <Loader2 size={12} className="animate-spin" />, label: "Thinking" },
  executing: { color: "bg-amber-500", icon: <Cpu size={12} />, label: "Executing" },
  delegating: { color: "bg-purple-500", icon: <ArrowRightLeft size={12} />, label: "Delegating" },
  done: { color: "bg-emerald-500", icon: <CheckCircle2 size={12} />, label: "Done" },
  error: { color: "bg-red-500", icon: <AlertCircle size={12} />, label: "Error" },
};

function AgentCard({ agent }: { agent: AgentState }) {
  const cfg = STATE_CONFIG[agent.state] || STATE_CONFIG.idle;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Bot size={18} className="text-zinc-400" />
          <div>
            <h3 className="text-sm font-medium text-zinc-100">{agent.name}</h3>
            {agent.is_main && (
              <span className="text-[10px] uppercase tracking-wider text-emerald-400 font-medium">
                Main
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${cfg.color}`} />
          <span className="text-xs text-zinc-400">{cfg.label}</span>
        </div>
      </div>

      {agent.description && (
        <p className="text-xs text-zinc-500 line-clamp-2">{agent.description}</p>
      )}

      <div className="flex items-center gap-2 text-[11px] text-zinc-500">
        <span className="bg-zinc-800 rounded px-1.5 py-0.5">{agent.llm_provider}</span>
        <span className="bg-zinc-800 rounded px-1.5 py-0.5">{agent.llm_model}</span>
      </div>
    </div>
  );
}

export function AgentGrid({ agents }: { agents: AgentState[] }) {
  if (agents.length === 0) {
    return (
      <div className="text-center py-8 text-zinc-500 text-sm">
        No agents configured
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
