"use client";

import { cn } from "@/lib/utils";

const STATE_COLORS: Record<string, string> = {
  idle: "bg-zinc-500",
  thinking: "bg-amber-500 animate-pulse",
  executing_tool: "bg-blue-500 animate-pulse",
  awaiting_approval: "bg-orange-500 animate-pulse",
  completed: "bg-emerald-500",
  failed: "bg-red-500",
};

export function AgentStateIndicator({ state }: { state: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={cn("h-2 w-2 rounded-full", STATE_COLORS[state] || "bg-zinc-500")} />
      <span className="text-xs text-zinc-400 capitalize">{state.replace("_", " ")}</span>
    </div>
  );
}
