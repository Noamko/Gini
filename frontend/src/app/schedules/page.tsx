"use client";

import { useEffect, useState, useCallback } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { api } from "@/lib/api-client";
import {
  Plus, Trash2, Clock, Bot, ToggleLeft, ToggleRight, Pencil, X, CalendarClock, GitBranch,
} from "lucide-react";

interface Schedule {
  id: string;
  agent_id: string | null;
  agent_name: string | null;
  workflow_id: string | null;
  workflow_name: string | null;
  name: string;
  cron_expression: string;
  instructions: string | null;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
}

interface AgentOption {
  id: string;
  name: string;
}

interface WorkflowOption {
  id: string;
  name: string;
}

const CRON_PRESETS = [
  { label: "Every 5 minutes", value: "*/5 * * * *" },
  { label: "Every 15 minutes", value: "*/15 * * * *" },
  { label: "Every hour", value: "0 * * * *" },
  { label: "Every morning at 8am", value: "0 8 * * *" },
  { label: "Every evening at 6pm", value: "0 18 * * *" },
  { label: "Daily at midnight", value: "0 0 * * *" },
  { label: "Weekdays at 9am", value: "0 9 * * 1-5" },
  { label: "Every Monday at 9am", value: "0 9 * * 1" },
];

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function SchedulesPage() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Schedule | null>(null);

  // Form state
  const [name, setName] = useState("");
  const [targetType, setTargetType] = useState<"agent" | "workflow">("agent");
  const [agentId, setAgentId] = useState("");
  const [workflowId, setWorkflowId] = useState("");
  const [cron, setCron] = useState("0 8 * * *");
  const [instructions, setInstructions] = useState("");
  const [saving, setSaving] = useState(false);

  const loadSchedules = useCallback(async () => {
    try {
      const [schedData, agentData, wfData] = await Promise.all([
        api.schedules.list(),
        api.agents.list(),
        api.workflows.list(),
      ]);
      setSchedules(schedData.items);
      setAgents(agentData.items.map((a: any) => ({ id: a.id, name: a.name })));
      setWorkflows(wfData.items.map((w: any) => ({ id: w.id, name: w.name })));
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    loadSchedules();
  }, [loadSchedules]);

  const resetForm = () => {
    setName(""); setAgentId(""); setWorkflowId(""); setTargetType("agent");
    setCron("0 8 * * *"); setInstructions("");
    setShowForm(false); setEditing(null);
  };

  const openEdit = (s: Schedule) => {
    setEditing(s);
    setName(s.name);
    setTargetType(s.workflow_id ? "workflow" : "agent");
    setAgentId(s.agent_id || "");
    setWorkflowId(s.workflow_id || "");
    setCron(s.cron_expression);
    setInstructions(s.instructions || "");
    setShowForm(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editing) {
        await api.schedules.update(editing.id, {
          name, cron_expression: cron, instructions: instructions || null,
        });
      } else {
        await api.schedules.create({
          agent_id: targetType === "agent" ? agentId : undefined,
          workflow_id: targetType === "workflow" ? workflowId : undefined,
          name, cron_expression: cron, instructions: instructions || null,
        });
      }
      resetForm();
      await loadSchedules();
    } catch {}
    setSaving(false);
  };

  const handleToggle = async (s: Schedule) => {
    await api.schedules.update(s.id, { enabled: !s.enabled });
    await loadSchedules();
  };

  const handleDelete = async (s: Schedule) => {
    if (confirm(`Delete schedule "${s.name}"?`)) {
      await api.schedules.delete(s.id);
      await loadSchedules();
    }
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-3 pt-14 md:p-6 md:pt-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Schedules</h1>
              <p className="text-sm text-zinc-500 mt-1">Run agents automatically on a schedule</p>
            </div>
            <button
              onClick={() => { resetForm(); setShowForm(true); }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm transition-colors"
            >
              <Plus size={16} />
              New Schedule
            </button>
          </div>

          {/* Form */}
          {showForm && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">{editing ? "Edit Schedule" : "Create Schedule"}</h2>
                <button onClick={resetForm} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400">
                  <X size={18} />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-400">Name</label>
                  <input value={name} onChange={(e) => setName(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
                    placeholder="e.g. Morning email check" />
                </div>
                {!editing && (
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-zinc-400">Target</label>
                    <div className="flex gap-2">
                      <select value={targetType} onChange={(e) => setTargetType(e.target.value as "agent" | "workflow")}
                        className="bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500">
                        <option value="agent">Agent</option>
                        <option value="workflow">Workflow</option>
                      </select>
                      {targetType === "agent" ? (
                        <select value={agentId} onChange={(e) => setAgentId(e.target.value)}
                          className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500">
                          <option value="">Select an agent...</option>
                          {agents.map((a) => (
                            <option key={a.id} value={a.id}>{a.name}</option>
                          ))}
                        </select>
                      ) : (
                        <select value={workflowId} onChange={(e) => setWorkflowId(e.target.value)}
                          className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500">
                          <option value="">Select a workflow...</option>
                          {workflows.map((w) => (
                            <option key={w.id} value={w.id}>{w.name}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400">Cron Expression</label>
                <div className="flex gap-2">
                  <input value={cron} onChange={(e) => setCron(e.target.value)}
                    className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-violet-500"
                    placeholder="*/15 * * * *" />
                  <select onChange={(e) => { if (e.target.value) setCron(e.target.value); }}
                    className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
                    value="">
                    <option value="">Presets...</option>
                    {CRON_PRESETS.map((p) => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400">Instructions (optional)</label>
                <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)}
                  rows={2}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-violet-500"
                  placeholder="e.g. Check my unread emails and send a summary to Telegram" />
              </div>

              <div className="flex justify-end gap-2">
                <button onClick={resetForm}
                  className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:bg-zinc-800 transition-colors">
                  Cancel
                </button>
                <button onClick={handleSave}
                  disabled={saving || !name || (!editing && !agentId && !workflowId) || !cron}
                  className="px-4 py-2 rounded-lg text-sm bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 disabled:text-zinc-500 transition-colors">
                  {saving ? "Saving..." : editing ? "Update" : "Create"}
                </button>
              </div>
            </div>
          )}

          {/* Schedule list */}
          {loading ? (
            <p className="text-sm text-zinc-500">Loading schedules...</p>
          ) : schedules.length === 0 ? (
            <div className="text-center py-12 text-zinc-500">
              <CalendarClock size={32} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm">No schedules yet. Create one to run agents automatically.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {schedules.map((s) => (
                <div key={s.id}
                  className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex items-center justify-between hover:border-zinc-700 transition-colors">
                  <div className="flex items-center gap-3 min-w-0">
                    <button onClick={() => handleToggle(s)} className="shrink-0">
                      {s.enabled
                        ? <ToggleRight size={24} className="text-emerald-400" />
                        : <ToggleLeft size={24} className="text-zinc-600" />}
                    </button>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`text-sm font-medium ${s.enabled ? "text-zinc-100" : "text-zinc-500"}`}>
                          {s.name}
                        </span>
                        <span className="text-[11px] bg-zinc-800 rounded px-1.5 py-0.5 text-zinc-500 font-mono">
                          {s.cron_expression}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-zinc-500 mt-0.5">
                        <span className="flex items-center gap-1">
                          {s.workflow_name ? <><GitBranch size={10} /> {s.workflow_name}</> : <><Bot size={10} /> {s.agent_name}</>}
                        </span>
                        {s.instructions && (
                          <span className="truncate max-w-[200px]">{s.instructions}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-zinc-600 mt-0.5">
                        <span>Last: {formatTime(s.last_run_at)}</span>
                        <span>Next: {formatTime(s.next_run_at)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0 ml-3">
                    <button onClick={() => openEdit(s)}
                      className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors">
                      <Pencil size={14} />
                    </button>
                    <button onClick={() => handleDelete(s)}
                      className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-red-400 transition-colors">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
