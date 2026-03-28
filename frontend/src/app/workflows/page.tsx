"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { api } from "@/lib/api-client";
import {
  Plus, Trash2, Bot, Play, Pencil, X, ArrowDown, GitBranch, ChevronDown, ChevronUp, Loader2,
} from "lucide-react";

interface WorkflowStep {
  agent_id: string;
  agent_name: string | null;
  instructions: string;
  pass_output: boolean;
}

interface WorkflowItem {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  steps: WorkflowStep[];
  created_at: string;
}

interface AgentOption { id: string; name: string; }

export default function WorkflowsPage() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<WorkflowItem | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  // Form
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState<WorkflowStep[]>([]);
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [wfData, agData] = await Promise.all([api.workflows.list(), api.agents.list()]);
      setWorkflows(wfData.items);
      setAgents(agData.items.map((a: any) => ({ id: a.id, name: a.name })));
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const resetForm = () => {
    setName(""); setDescription(""); setSteps([]); setShowForm(false); setEditing(null);
  };

  const openEdit = (w: WorkflowItem) => {
    setEditing(w); setName(w.name); setDescription(w.description || "");
    setSteps(w.steps.map((s) => ({ ...s }))); setShowForm(true);
  };

  const addStep = () => {
    setSteps([...steps, { agent_id: "", agent_name: null, instructions: "", pass_output: true }]);
  };

  const updateStep = (i: number, field: string, value: any) => {
    const next = [...steps];
    (next[i] as any)[field] = value;
    if (field === "agent_id") {
      next[i].agent_name = agents.find((a) => a.id === value)?.name || null;
    }
    setSteps(next);
  };

  const removeStep = (i: number) => setSteps(steps.filter((_, idx) => idx !== i));

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { name, description: description || null, steps };
      if (editing) {
        await api.workflows.update(editing.id, payload);
      } else {
        await api.workflows.create(payload);
      }
      resetForm(); await loadData();
    } catch {}
    setSaving(false);
  };

  const handleRun = async (w: WorkflowItem) => {
    setRunning(w.id);
    try {
      await api.workflows.run(w.id);
      router.push("/runs");
    } catch (e: any) {
      alert(`Failed to start: ${e.message}`);
      setRunning(null);
    }
  };

  const handleDelete = async (w: WorkflowItem) => {
    if (confirm(`Delete workflow "${w.name}"?`)) {
      await api.workflows.delete(w.id); await loadData();
    }
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-3 pt-14 md:p-6 md:pt-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Workflows</h1>
              <p className="text-sm text-zinc-500 mt-1">Chain agents into multi-step pipelines</p>
            </div>
            <button onClick={() => { resetForm(); setShowForm(true); }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm transition-colors">
              <Plus size={16} /> New Workflow
            </button>
          </div>

          {/* Form */}
          {showForm && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">{editing ? "Edit Workflow" : "Create Workflow"}</h2>
                <button onClick={resetForm} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400"><X size={18} /></button>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-400">Name</label>
                  <input value={name} onChange={(e) => setName(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
                    placeholder="e.g. Morning Email Summary" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-400">Description</label>
                  <input value={description} onChange={(e) => setDescription(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
                    placeholder="What does this workflow do?" />
                </div>
              </div>

              {/* Steps */}
              <div className="space-y-2">
                <label className="text-xs font-medium text-zinc-400">Steps</label>
                {steps.map((step, i) => (
                  <div key={i} className="flex gap-2 items-start">
                    {i > 0 && (
                      <div className="flex flex-col items-center pt-2 -mt-3">
                        <ArrowDown size={14} className="text-zinc-600" />
                      </div>
                    )}
                    <div className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg p-3 space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-zinc-500 font-mono w-6">#{i + 1}</span>
                        <select value={step.agent_id} onChange={(e) => updateStep(i, "agent_id", e.target.value)}
                          className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500">
                          <option value="">Select agent...</option>
                          {agents.map((a) => (<option key={a.id} value={a.id}>{a.name}</option>))}
                        </select>
                        <label className="flex items-center gap-1 text-[11px] text-zinc-500">
                          <input type="checkbox" checked={step.pass_output}
                            onChange={(e) => updateStep(i, "pass_output", e.target.checked)}
                            className="w-3 h-3 rounded" />
                          Chain
                        </label>
                        <button onClick={() => removeStep(i)}
                          className="p-1 rounded hover:bg-zinc-700 text-zinc-500 hover:text-red-400">
                          <X size={12} />
                        </button>
                      </div>
                      <input value={step.instructions} onChange={(e) => updateStep(i, "instructions", e.target.value)}
                        className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500"
                        placeholder="Instructions for this step..." />
                    </div>
                  </div>
                ))}
                <button onClick={addStep}
                  className="w-full border border-dashed border-zinc-700 rounded-lg py-2 text-xs text-zinc-500 hover:text-zinc-300 hover:border-zinc-600 transition-colors">
                  + Add Step
                </button>
              </div>

              <div className="flex justify-end gap-2">
                <button onClick={resetForm} className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:bg-zinc-800">Cancel</button>
                <button onClick={handleSave}
                  disabled={saving || !name || steps.length === 0 || steps.some((s) => !s.agent_id)}
                  className="px-4 py-2 rounded-lg text-sm bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 disabled:text-zinc-500">
                  {saving ? "Saving..." : editing ? "Update" : "Create"}
                </button>
              </div>
            </div>
          )}

          {/* Workflow list */}
          {loading ? (
            <p className="text-sm text-zinc-500">Loading workflows...</p>
          ) : workflows.length === 0 ? (
            <div className="text-center py-12 text-zinc-500">
              <GitBranch size={32} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm">No workflows yet. Chain agents together for multi-step automation.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {workflows.map((w) => (
                <div key={w.id} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden hover:border-zinc-700 transition-colors">
                  <div className="flex items-center justify-between px-4 py-3">
                    <button onClick={() => setExpandedId(expandedId === w.id ? null : w.id)}
                      className="flex items-center gap-3 text-left flex-1 min-w-0">
                      <GitBranch size={16} className="text-violet-400 shrink-0" />
                      <div className="min-w-0">
                        <span className="text-sm font-medium">{w.name}</span>
                        <div className="text-[11px] text-zinc-500">
                          {w.steps.length} steps: {w.steps.map((s) => s.agent_name || "?").join(" → ")}
                        </div>
                      </div>
                      {expandedId === w.id ? <ChevronUp size={14} className="text-zinc-500" /> : <ChevronDown size={14} className="text-zinc-500" />}
                    </button>
                    <div className="flex items-center gap-1 ml-3">
                      <button onClick={() => handleRun(w)}
                        disabled={running === w.id}
                        className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-emerald-400 transition-colors disabled:text-emerald-400">
                        {running === w.id ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                      </button>
                      <button onClick={() => openEdit(w)}
                        className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => handleDelete(w)}
                        className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-red-400">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  {expandedId === w.id && (
                    <div className="border-t border-zinc-800 px-4 py-3 space-y-2">
                      {w.description && <p className="text-xs text-zinc-400">{w.description}</p>}
                      {w.steps.map((s, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <span className="text-[11px] text-zinc-600 font-mono w-5">#{i + 1}</span>
                          <Bot size={12} className="text-violet-400" />
                          <span className="text-xs text-zinc-300">{s.agent_name}</span>
                          {s.instructions && <span className="text-[11px] text-zinc-500 truncate">— {s.instructions}</span>}
                          {s.pass_output && i > 0 && <span className="text-[10px] bg-zinc-800 rounded px-1 text-zinc-500">chained</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
