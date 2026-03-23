"use client";

import { useEffect, useState, useCallback } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { api } from "@/lib/api-client";
import {
  Plus, Trash2, Bot, ToggleLeft, ToggleRight, Pencil, X, Webhook, Copy, Check,
} from "lucide-react";

interface WebhookItem {
  id: string;
  agent_id: string;
  agent_name: string;
  name: string;
  token: string;
  url: string;
  instructions_template: string | null;
  enabled: boolean;
  created_at: string;
}

interface AgentOption {
  id: string;
  name: string;
}

export default function WebhooksPage() {
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([]);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<WebhookItem | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [agentId, setAgentId] = useState("");
  const [template, setTemplate] = useState("");
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [whData, agData] = await Promise.all([
        api.webhooks.list(),
        api.agents.list(),
      ]);
      setWebhooks(whData.items);
      setAgents(agData.items.map((a: any) => ({ id: a.id, name: a.name })));
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const resetForm = () => {
    setName(""); setAgentId(""); setTemplate("");
    setShowForm(false); setEditing(null);
  };

  const openEdit = (w: WebhookItem) => {
    setEditing(w); setName(w.name); setAgentId(w.agent_id);
    setTemplate(w.instructions_template || ""); setShowForm(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editing) {
        await api.webhooks.update(editing.id, { name, instructions_template: template || null });
      } else {
        await api.webhooks.create({ agent_id: agentId, name, instructions_template: template || null });
      }
      resetForm(); await loadData();
    } catch {}
    setSaving(false);
  };

  const handleToggle = async (w: WebhookItem) => {
    await api.webhooks.update(w.id, { enabled: !w.enabled });
    await loadData();
  };

  const handleDelete = async (w: WebhookItem) => {
    if (confirm(`Delete webhook "${w.name}"?`)) {
      await api.webhooks.delete(w.id); await loadData();
    }
  };

  const copyUrl = (w: WebhookItem) => {
    navigator.clipboard.writeText(w.url);
    setCopiedId(w.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-3 pt-14 md:p-6 md:pt-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Webhooks</h1>
              <p className="text-sm text-zinc-500 mt-1">Trigger agent runs from external events</p>
            </div>
            <button onClick={() => { resetForm(); setShowForm(true); }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm transition-colors">
              <Plus size={16} /> New Webhook
            </button>
          </div>

          {showForm && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">{editing ? "Edit Webhook" : "Create Webhook"}</h2>
                <button onClick={resetForm} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400"><X size={18} /></button>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-400">Name</label>
                  <input value={name} onChange={(e) => setName(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
                    placeholder="e.g. GitHub PR Webhook" />
                </div>
                {!editing && (
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-zinc-400">Agent</label>
                    <select value={agentId} onChange={(e) => setAgentId(e.target.value)}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500">
                      <option value="">Select an agent...</option>
                      {agents.map((a) => (<option key={a.id} value={a.id}>{a.name}</option>))}
                    </select>
                  </div>
                )}
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400">Instructions Template (optional)</label>
                <textarea value={template} onChange={(e) => setTemplate(e.target.value)} rows={3}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-violet-500"
                  placeholder="e.g. Review this GitHub PR and post a summary to Telegram. The PR details are in the payload below." />
                <p className="text-[11px] text-zinc-600">The webhook payload will be appended automatically.</p>
              </div>
              <div className="flex justify-end gap-2">
                <button onClick={resetForm} className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:bg-zinc-800">Cancel</button>
                <button onClick={handleSave} disabled={saving || !name || (!editing && !agentId)}
                  className="px-4 py-2 rounded-lg text-sm bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 disabled:text-zinc-500">
                  {saving ? "Saving..." : editing ? "Update" : "Create"}
                </button>
              </div>
            </div>
          )}

          {loading ? (
            <p className="text-sm text-zinc-500">Loading webhooks...</p>
          ) : webhooks.length === 0 ? (
            <div className="text-center py-12 text-zinc-500">
              <Webhook size={32} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm">No webhooks yet. Create one to trigger agents from external services.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {webhooks.map((w) => (
                <div key={w.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-2 hover:border-zinc-700 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <button onClick={() => handleToggle(w)} className="shrink-0">
                        {w.enabled ? <ToggleRight size={24} className="text-emerald-400" /> : <ToggleLeft size={24} className="text-zinc-600" />}
                      </button>
                      <div>
                        <span className={`text-sm font-medium ${w.enabled ? "text-zinc-100" : "text-zinc-500"}`}>{w.name}</span>
                        <div className="flex items-center gap-2 text-[11px] text-zinc-500 mt-0.5">
                          <Bot size={10} /> {w.agent_name}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button onClick={() => copyUrl(w)}
                        className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
                        title="Copy URL">
                        {copiedId === w.id ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                      </button>
                      <button onClick={() => openEdit(w)}
                        className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => handleDelete(w)}
                        className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-red-400 transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <code className="text-[11px] text-zinc-500 bg-zinc-800 rounded px-2 py-1 font-mono truncate flex-1">
                      POST {w.url}
                    </code>
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
