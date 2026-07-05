"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api-client";
import { Sidebar } from "@/components/layout/Sidebar";
import { Plus, Pencil, Trash2, Zap, Users, Shield, Check, X } from "lucide-react";

interface Skill {
  id: string;
  name: string;
  description: string | null;
  instructions: string;
  is_active: boolean;
  tools: { id: string; name: string; description: string }[];
  credentials: { id: string; name: string; credential_type: string }[];
}

interface ToolOption {
  id: string;
  name: string;
  description: string;
}

interface CredentialOption {
  id: string;
  name: string;
  credential_type: string;
}

interface AgentLite {
  id: string;
  name: string;
  is_main: boolean;
  is_active: boolean;
}

// Tools that let an agent create/manage other agents — skills bundling these grant powerful,
// approval-gated capabilities, so we flag them in the UI.
const META_TOOL_NAMES = new Set([
  "create_agent",
  "list_agents",
  "create_workflow",
  "create_webhook",
  "create_tool",
]);

const grantsMetaTools = (skill: Skill) => skill.tools.some((t) => META_TOOL_NAMES.has(t.name));

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [tools, setTools] = useState<ToolOption[]>([]);
  const [credentials, setCredentials] = useState<CredentialOption[]>([]);
  const [agents, setAgents] = useState<AgentLite[]>([]);
  // skillId -> agents that have it assigned
  const [assignments, setAssignments] = useState<Record<string, AgentLite[]>>({});
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Skill | null>(null);
  const [managing, setManaging] = useState<Skill | null>(null);
  const [assignBusy, setAssignBusy] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [selectedToolIds, setSelectedToolIds] = useState<string[]>([]);
  const [selectedCredIds, setSelectedCredIds] = useState<string[]>([]);

  const loadAssignments = useCallback(async (skillList: Skill[]) => {
    const entries = await Promise.all(
      skillList.map(async (s) => {
        try {
          return [s.id, await api.skills.agents(s.id)] as const;
        } catch {
          return [s.id, [] as AgentLite[]] as const;
        }
      })
    );
    setAssignments(Object.fromEntries(entries));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, t, c, a] = await Promise.all([
        api.skills.list(),
        api.tools.list(),
        api.credentials.list(),
        api.agents.list(0, 200),
      ]);
      setSkills(s);
      setTools(t);
      setCredentials(c);
      setAgents(a.items ?? []);
      await loadAssignments(s);
    } catch {
      // ignore
    }
    setLoading(false);
  }, [loadAssignments]);

  useEffect(() => {
    load();
  }, [load]);

  const resetForm = () => {
    setName("");
    setDescription("");
    setInstructions("");
    setSelectedToolIds([]);
    setSelectedCredIds([]);
    setEditing(null);
    setShowForm(false);
  };

  const openEdit = (skill: Skill) => {
    setName(skill.name);
    setDescription(skill.description || "");
    setInstructions(skill.instructions);
    setSelectedToolIds(skill.tools.map((t) => t.id));
    setSelectedCredIds(skill.credentials.map((c) => c.id));
    setEditing(skill);
    setShowForm(true);
  };

  const handleSave = async () => {
    const data = {
      name,
      description: description || null,
      instructions,
      tool_ids: selectedToolIds,
      credential_ids: selectedCredIds,
    };

    if (editing) {
      await api.skills.update(editing.id, data);
    } else {
      await api.skills.create(data);
    }
    resetForm();
    load();
  };

  const handleDelete = async (skill: Skill) => {
    if (!confirm(`Delete skill "${skill.name}"?`)) return;
    await api.skills.delete(skill.id);
    load();
  };

  const toggleTool = (id: string) => {
    setSelectedToolIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const toggleCred = (id: string) => {
    setSelectedCredIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const isAssigned = (skillId: string, agentId: string) =>
    (assignments[skillId] ?? []).some((a) => a.id === agentId);

  const toggleAgent = async (skill: Skill, agent: AgentLite) => {
    setAssignBusy(agent.id);
    try {
      if (isAssigned(skill.id, agent.id)) {
        await api.skills.unassign(skill.id, agent.id);
      } else {
        await api.skills.assign(skill.id, agent.id);
      }
      const updated = await api.skills.agents(skill.id);
      setAssignments((prev) => ({ ...prev, [skill.id]: updated }));
    } catch {
      // ignore
    } finally {
      setAssignBusy(null);
    }
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-3 pt-14 md:p-6 md:pt-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Skills</h1>
              <p className="text-sm text-zinc-500 mt-1">
                Reusable workflows that combine tools and credentials
              </p>
            </div>
            <button
              onClick={() => {
                resetForm();
                setShowForm(true);
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm transition-colors"
            >
              <Plus size={16} />
              New Skill
            </button>
          </div>

          {showForm && (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 space-y-4">
              <h2 className="text-lg font-semibold">
                {editing ? "Edit Skill" : "Create Skill"}
              </h2>

              <div>
                <label className="block text-xs text-zinc-500 mb-1">Name</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                  placeholder="e.g. GitHub PR Review"
                />
              </div>

              <div>
                <label className="block text-xs text-zinc-500 mb-1">Description</label>
                <input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                  placeholder="What does this skill do?"
                />
              </div>

              <div>
                <label className="block text-xs text-zinc-500 mb-1">Instructions</label>
                <textarea
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  rows={4}
                  className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-violet-500 resize-none"
                  placeholder="Step-by-step instructions for the agent..."
                />
              </div>

              {tools.length > 0 && (
                <div>
                  <label className="block text-xs text-zinc-500 mb-2">Tools</label>
                  <div className="flex flex-wrap gap-2">
                    {tools.map((t) => (
                      <button
                        key={t.id}
                        onClick={() => toggleTool(t.id)}
                        className={`px-3 py-1 rounded-full text-xs transition-colors ${
                          selectedToolIds.includes(t.id)
                            ? "bg-violet-600 text-white"
                            : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                        }`}
                      >
                        {t.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {credentials.length > 0 && (
                <div>
                  <label className="block text-xs text-zinc-500 mb-2">Credentials</label>
                  <div className="flex flex-wrap gap-2">
                    {credentials.map((c) => (
                      <button
                        key={c.id}
                        onClick={() => toggleCred(c.id)}
                        className={`px-3 py-1 rounded-full text-xs transition-colors ${
                          selectedCredIds.includes(c.id)
                            ? "bg-emerald-600 text-white"
                            : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                        }`}
                      >
                        {c.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <button
                  onClick={handleSave}
                  disabled={!name.trim()}
                  className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm disabled:opacity-50 transition-colors"
                >
                  {editing ? "Update" : "Create"}
                </button>
                <button
                  onClick={resetForm}
                  className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {loading ? (
            <p className="text-sm text-zinc-500">Loading skills...</p>
          ) : skills.length === 0 ? (
            <div className="text-center py-12 text-zinc-500">
              <Zap size={32} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm">No skills yet. Create one to get started.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {skills.map((skill) => {
                const assigned = assignments[skill.id] ?? [];
                return (
                  <div
                    key={skill.id}
                    className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 space-y-3"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-semibold flex items-center gap-2">
                          <Zap size={14} className="text-violet-400" />
                          {skill.name}
                          {grantsMetaTools(skill) && (
                            <span
                              title="Grants agent-management tools (create agents/workflows/webhooks/tools). Assign with care."
                              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-500/15 text-[10px] text-amber-400"
                            >
                              <Shield size={10} />
                              Powerful
                            </span>
                          )}
                        </h3>
                        {skill.description && (
                          <p className="text-xs text-zinc-500 mt-1">{skill.description}</p>
                        )}
                      </div>
                      <div className="flex gap-1">
                        <button
                          onClick={() => setManaging(skill)}
                          title="Manage agents"
                          className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
                        >
                          <Users size={14} />
                        </button>
                        <button
                          onClick={() => openEdit(skill)}
                          className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          onClick={() => handleDelete(skill)}
                          className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-red-400 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>

                    {skill.tools.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {skill.tools.map((t) => (
                          <span
                            key={t.id}
                            className="px-2 py-0.5 rounded-full bg-zinc-800 text-[11px] text-violet-400"
                          >
                            {t.name}
                          </span>
                        ))}
                      </div>
                    )}

                    {skill.credentials.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {skill.credentials.map((c) => (
                          <span
                            key={c.id}
                            className="px-2 py-0.5 rounded-full bg-zinc-800 text-[11px] text-emerald-400"
                          >
                            {c.name}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Assigned agents */}
                    <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-zinc-800/70">
                      <span className="text-[11px] text-zinc-600 mr-1 inline-flex items-center gap-1">
                        <Users size={11} /> Agents:
                      </span>
                      {assigned.length === 0 ? (
                        <button
                          onClick={() => setManaging(skill)}
                          className="text-[11px] text-zinc-500 hover:text-violet-400 transition-colors"
                        >
                          none — assign
                        </button>
                      ) : (
                        assigned.map((a) => (
                          <span
                            key={a.id}
                            className="px-2 py-0.5 rounded-full bg-zinc-800 text-[11px] text-sky-300"
                          >
                            {a.name}
                            {a.is_main && <span className="text-zinc-500"> ·main</span>}
                          </span>
                        ))
                      )}
                    </div>

                    <p className={`text-[11px] ${skill.is_active ? "text-emerald-400" : "text-zinc-600"}`}>
                      {skill.is_active ? "Active" : "Inactive"}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>

      {/* Manage agents modal */}
      {managing && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => setManaging(null)}
        >
          <div
            className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
              <div>
                <h2 className="text-sm font-semibold flex items-center gap-2">
                  <Users size={14} className="text-violet-400" />
                  Assign “{managing.name}” to agents
                </h2>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  Toggle an agent to grant or revoke this skill.
                </p>
              </div>
              <button
                onClick={() => setManaging(null)}
                className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400"
              >
                <X size={16} />
              </button>
            </div>

            {grantsMetaTools(managing) && (
              <div className="mx-5 mt-4 flex items-start gap-2 rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-[11px] text-amber-300/90">
                <Shield size={13} className="mt-0.5 shrink-0" />
                <span>
                  This skill lets an agent create other agents, workflows, webhooks, and tools. Create
                  actions require approval unless the agent is set to auto-approve.
                </span>
              </div>
            )}

            <div className="p-4 space-y-2 max-h-[60vh] overflow-y-auto">
              {agents.length === 0 ? (
                <p className="text-sm text-zinc-500 px-1 py-2">No agents found.</p>
              ) : (
                agents.map((agent) => {
                  const on = isAssigned(managing.id, agent.id);
                  const busy = assignBusy === agent.id;
                  return (
                    <button
                      key={agent.id}
                      onClick={() => toggleAgent(managing, agent)}
                      disabled={busy}
                      className={`w-full flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left text-sm transition-colors disabled:opacity-50 ${
                        on
                          ? "bg-violet-600/20 border-violet-500/50 text-violet-200"
                          : "bg-zinc-800 border-zinc-700 text-zinc-300 hover:border-zinc-600"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        {agent.name}
                        {agent.is_main && (
                          <span className="px-1.5 py-0.5 rounded-full bg-zinc-700 text-[10px] text-zinc-300">
                            main
                          </span>
                        )}
                        {!agent.is_active && (
                          <span className="text-[10px] text-zinc-600">inactive</span>
                        )}
                      </span>
                      <span className="text-[11px] text-zinc-400">
                        {busy ? "…" : on ? <Check size={14} className="text-violet-300" /> : "Assign"}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
