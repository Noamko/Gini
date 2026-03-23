"use client";

import { useEffect, useState } from "react";
import type { Agent } from "@/lib/types";
import { api } from "@/lib/api-client";
import { AgentStateIndicator } from "./AgentStateIndicator";
import { Bot, Crown, Pencil, Trash2, Play, Sparkles, KeyRound, ShieldCheck } from "lucide-react";

interface SkillInfo {
  id: string;
  name: string;
  credentials: { id: string; name: string }[];
}

interface Props {
  agent: Agent;
  onEdit: (agent: Agent) => void;
  onDelete: (agent: Agent) => void;
  onRun: (agent: Agent) => void;
}

export function AgentCard({ agent, onEdit, onDelete, onRun }: Props) {
  const [skills, setSkills] = useState<SkillInfo[]>([]);

  useEffect(() => {
    api.agents.skills(agent.id).then((data) => setSkills(data)).catch(() => {});
  }, [agent.id, agent.updated_at]);

  const allCredentials = skills.flatMap((s) => s.credentials);
  const uniqueCredentials = allCredentials.filter(
    (c, i, arr) => arr.findIndex((x) => x.id === c.id) === i
  );

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3 hover:border-zinc-700 transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-violet-600/20 flex items-center justify-center">
            <Bot size={18} className="text-violet-400" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h3 className="font-medium text-sm">{agent.name}</h3>
              {agent.is_main && <Crown size={12} className="text-amber-400" />}
            </div>
            <p className="text-xs text-zinc-500">{agent.llm_model}</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onRun(agent)}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-emerald-400 transition-colors"
            title="Run agent"
          >
            <Play size={14} />
          </button>
          <button
            onClick={() => onEdit(agent)}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <Pencil size={14} />
          </button>
          {!agent.is_main && (
            <button
              onClick={() => onDelete(agent)}
              className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-red-400 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {agent.description && (
        <p className="text-xs text-zinc-400 line-clamp-2">{agent.description}</p>
      )}

      {skills.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {skills.map((s) => (
            <span
              key={s.id}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-violet-600/10 border border-violet-800/30 text-[11px] text-violet-300"
            >
              <Sparkles size={10} />
              {s.name}
            </span>
          ))}
        </div>
      )}

      {uniqueCredentials.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {uniqueCredentials.map((c) => (
            <span
              key={c.id}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-600/10 border border-amber-800/30 text-[11px] text-amber-300"
            >
              <KeyRound size={10} />
              {c.name}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AgentStateIndicator state={agent.state} />
          {agent.auto_approve && (
            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400">
              <ShieldCheck size={10} />
              Trusted
            </span>
          )}
        </div>
        <span className="text-[11px] text-zinc-600">{agent.llm_provider}</span>
      </div>
    </div>
  );
}
