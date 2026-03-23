"use client";

import { useState } from "react";
import type { Agent } from "@/lib/types";
import { X, Play, Bot } from "lucide-react";

interface Props {
  agent: Agent;
  onRun: (agent: Agent, instructions: string) => Promise<void>;
  onClose: () => void;
}

export function RunAgentDialog({ agent, onRun, onClose }: Props) {
  const [instructions, setInstructions] = useState("");
  const [running, setRunning] = useState(false);

  const handleRun = async () => {
    setRunning(true);
    try {
      await onRun(agent, instructions.trim());
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-lg mx-4 shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-violet-600/20 flex items-center justify-center">
              <Bot size={16} className="text-violet-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold">Run {agent.name}</h2>
              <p className="text-[11px] text-zinc-500">{agent.llm_model}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {agent.description && (
            <p className="text-xs text-zinc-400">{agent.description}</p>
          )}

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">
              Instructions (optional)
            </label>
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={3}
              placeholder={`e.g. "Fetch my 5 unread emails" or "Summarize today's PRs"`}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-violet-500 placeholder-zinc-500"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleRun();
                }
              }}
              autoFocus
            />
            <p className="text-[11px] text-zinc-600">
              Leave blank to start a general conversation with this agent.
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-zinc-800">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:bg-zinc-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleRun}
            disabled={running}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-700 disabled:text-zinc-500 transition-colors"
          >
            <Play size={14} />
            {running ? "Starting..." : "Run"}
          </button>
        </div>
      </div>
    </div>
  );
}
