"use client";

import { useState, useEffect, useCallback } from "react";
import type { Agent } from "@/lib/types";
import { api } from "@/lib/api-client";
import { X, Sparkles, KeyRound, Check } from "lucide-react";

interface Props {
  agent?: Agent | null;
  onSave: (data: Partial<Agent>) => Promise<void>;
  onCancel: () => void;
  onDone?: () => void;
}

interface SkillOption {
  id: string;
  name: string;
  description: string | null;
}

interface CredentialOption {
  id: string;
  name: string;
  credential_type: string;
}

const PROVIDERS = [
  { value: "anthropic", label: "Anthropic" },
  { value: "openai", label: "OpenAI" },
];

const MODELS: Record<string, { value: string; label: string }[]> = {
  anthropic: [
    { value: "claude-opus-4-20250514", label: "Claude Opus 4" },
    { value: "claude-sonnet-4-20250514", label: "Claude Sonnet 4" },
    { value: "claude-3-5-sonnet-20241022", label: "Claude 3.5 Sonnet" },
    { value: "claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku" },
    { value: "claude-3-opus-20240229", label: "Claude 3 Opus" },
    { value: "claude-3-sonnet-20240229", label: "Claude 3 Sonnet" },
    { value: "claude-3-haiku-20240307", label: "Claude 3 Haiku" },
  ],
  openai: [
    { value: "gpt-4o", label: "GPT-4o" },
    { value: "gpt-4o-mini", label: "GPT-4o Mini" },
    { value: "gpt-4-turbo", label: "GPT-4 Turbo" },
    { value: "gpt-4", label: "GPT-4" },
    { value: "gpt-3.5-turbo", label: "GPT-3.5 Turbo" },
    { value: "o1", label: "o1" },
    { value: "o1-mini", label: "o1 Mini" },
    { value: "o3", label: "o3" },
    { value: "o3-mini", label: "o3 Mini" },
    { value: "o4-mini", label: "o4 Mini" },
  ],
};

export function AgentForm({ agent, onSave, onCancel, onDone }: Props) {
  const [name, setName] = useState(agent?.name || "");
  const [description, setDescription] = useState(agent?.description || "");
  const [systemPrompt, setSystemPrompt] = useState(agent?.system_prompt || "");
  const [provider, setProvider] = useState(agent?.llm_provider || "anthropic");
  const [model, setModel] = useState(agent?.llm_model || "claude-sonnet-4-20250514");
  const [temperature, setTemperature] = useState(agent?.temperature ?? 0.7);
  const [maxTokens, setMaxTokens] = useState(agent?.max_tokens ?? 4096);
  const [autoApprove, setAutoApprove] = useState(agent?.auto_approve ?? false);
  const [dailyBudget, setDailyBudget] = useState(agent?.daily_budget_usd?.toString() || "");
  const [saving, setSaving] = useState(false);

  // Skills & credentials
  const [allSkills, setAllSkills] = useState<SkillOption[]>([]);
  const [allCredentials, setAllCredentials] = useState<CredentialOption[]>([]);
  const [assignedSkillIds, setAssignedSkillIds] = useState<Set<string>>(new Set());
  const [initialSkillIds, setInitialSkillIds] = useState<Set<string>>(new Set());

  const isEditing = !!agent;

  // Load available skills, credentials, and current assignments
  useEffect(() => {
    api.skills.list().then((data) => setAllSkills(data)).catch(() => {});
    api.credentials.list().then((data) => setAllCredentials(data)).catch(() => {});

    if (agent) {
      api.agents.skills(agent.id).then((skills) => {
        const ids = new Set(skills.map((s: any) => s.id));
        setAssignedSkillIds(ids);
        setInitialSkillIds(new Set(ids));
      }).catch(() => {});
    }
  }, [agent]);

  useEffect(() => {
    if (!agent) {
      const models = MODELS[provider];
      if (models?.length) setModel(models[0].value);
    }
  }, [provider, agent]);

  const toggleSkill = (skillId: string) => {
    setAssignedSkillIds((prev) => {
      const next = new Set(prev);
      if (next.has(skillId)) {
        next.delete(skillId);
      } else {
        next.add(skillId);
      }
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({
        name,
        description: description || null,
        system_prompt: systemPrompt,
        llm_provider: provider,
        llm_model: model,
        temperature,
        max_tokens: maxTokens,
        auto_approve: autoApprove,
        daily_budget_usd: dailyBudget ? parseFloat(dailyBudget) : null,
      } as Partial<Agent>);

      // Sync skill assignments if editing
      if (agent) {
        const added = [...assignedSkillIds].filter((id) => !initialSkillIds.has(id));
        const removed = [...initialSkillIds].filter((id) => !assignedSkillIds.has(id));
        await Promise.all([
          ...added.map((skillId) => api.skills.assign(skillId, agent.id)),
          ...removed.map((skillId) => api.skills.unassign(skillId, agent.id)),
        ]);
      }
      onDone?.();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">{isEditing ? "Edit Agent" : "Create Agent"}</h2>
        <button onClick={onCancel} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400">
          <X size={18} />
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
              placeholder="Agent name"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">Description</label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
              placeholder="What does this agent do?"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-zinc-400">System Prompt</label>
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            required
            rows={5}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-violet-500"
            placeholder="Define the agent's role and behavior..."
          />
        </div>

        <div className="grid grid-cols-4 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">Provider</label>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">Model</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
            >
              {(MODELS[provider] || []).map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">Temperature ({temperature})</label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={temperature}
              onChange={(e) => setTemperature(Number(e.target.value))}
              className="w-full mt-2"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">Max Tokens</label>
            <input
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(Number(e.target.value))}
              min={1}
              max={32000}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>
        </div>

        {/* Trust & execution */}
        <div className="space-y-3">
          <label className="text-xs font-medium text-zinc-400">Execution</label>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={autoApprove}
              onChange={(e) => setAutoApprove(e.target.checked)}
              className="w-4 h-4 rounded border-zinc-600 bg-zinc-800 text-violet-500 focus:ring-violet-500 focus:ring-offset-0"
            />
            <div>
              <span className="text-sm text-zinc-300">Trusted agent</span>
              <p className="text-[11px] text-zinc-500">
                Auto-approve tools, grant internet access in sandbox, inject credentials
              </p>
            </div>
          </label>
        </div>

        {/* Budget */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-zinc-400">Daily Budget (USD)</label>
          <input
            type="number"
            step="0.1"
            min="0"
            value={dailyBudget}
            onChange={(e) => setDailyBudget(e.target.value)}
            className="w-48 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
            placeholder="No limit"
          />
          <p className="text-[11px] text-zinc-500">Leave blank for unlimited. Runs are blocked when budget is exceeded.</p>
        </div>

        {/* Skills */}
        {allSkills.length > 0 && (
          <div className="space-y-2">
            <label className="text-xs font-medium text-zinc-400">Skills</label>
            <div className="flex flex-wrap gap-2">
              {allSkills.map((skill) => {
                const assigned = assignedSkillIds.has(skill.id);
                return (
                  <button
                    key={skill.id}
                    type="button"
                    onClick={() => toggleSkill(skill.id)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-colors ${
                      assigned
                        ? "bg-violet-600/20 border-violet-500/50 text-violet-300"
                        : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-600"
                    }`}
                  >
                    {assigned ? <Check size={12} /> : <Sparkles size={12} />}
                    {skill.name}
                  </button>
                );
              })}
            </div>
            {!isEditing && (
              <p className="text-[11px] text-zinc-600">Save the agent first, then edit to assign skills.</p>
            )}
          </div>
        )}

        {/* Credentials (read-only, inherited from skills) */}
        {isEditing && allCredentials.length > 0 && (
          <div className="space-y-2">
            <label className="text-xs font-medium text-zinc-400">Credentials (via skills)</label>
            <div className="flex flex-wrap gap-2">
              {allCredentials.map((cred) => (
                <span
                  key={cred.id}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-zinc-800 border border-zinc-700 text-[11px] text-zinc-400"
                >
                  <KeyRound size={10} />
                  {cred.name}
                  <span className="text-zinc-600">({cred.credential_type})</span>
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:bg-zinc-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || !name || !systemPrompt}
            className="px-4 py-2 rounded-lg text-sm bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 disabled:text-zinc-500 transition-colors"
          >
            {saving ? "Saving..." : isEditing ? "Update Agent" : "Create Agent"}
          </button>
        </div>
      </form>
    </div>
  );
}
