"use client";

import { useEffect, useState, useCallback } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { api } from "@/lib/api-client";
import {
  Plus, Wrench, Pencil, Trash2, X, ToggleLeft, ToggleRight, Upload, Code, ShieldCheck,
} from "lucide-react";

interface ToolItem {
  id: string;
  name: string;
  description: string;
  parameters_schema: Record<string, unknown>;
  implementation: string;
  requires_sandbox: boolean;
  requires_approval: boolean;
  is_builtin: boolean;
  is_active: boolean;
  code: string | null;
}

export default function ToolsPage() {
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<ToolItem | null>(null);

  // Form
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [paramsSchema, setParamsSchema] = useState('{\n  "type": "object",\n  "properties": {},\n  "required": []\n}');
  const [code, setCode] = useState('def execute(**kwargs):\n    """Your tool logic here. Return a string or dict."""\n    return "Hello from custom tool!"');
  const [requiresSandbox, setRequiresSandbox] = useState(false);
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadTools = useCallback(async () => {
    try {
      const items = await api.tools.list();
      setTools(items);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { loadTools(); }, [loadTools]);

  const resetForm = () => {
    setName(""); setDescription("");
    setParamsSchema('{\n  "type": "object",\n  "properties": {},\n  "required": []\n}');
    setCode('def execute(**kwargs):\n    """Your tool logic here. Return a string or dict."""\n    return "Hello from custom tool!"');
    setRequiresSandbox(false); setRequiresApproval(false);
    setShowForm(false); setEditing(null);
  };

  const openEdit = (t: ToolItem) => {
    setEditing(t); setName(t.name); setDescription(t.description);
    setParamsSchema(JSON.stringify(t.parameters_schema, null, 2));
    setCode(t.code || ""); setRequiresSandbox(t.requires_sandbox);
    setRequiresApproval(t.requires_approval); setShowForm(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      let schema: Record<string, unknown>;
      try { schema = JSON.parse(paramsSchema); } catch { alert("Invalid JSON in parameters schema"); setSaving(false); return; }

      if (editing) {
        await api.tools.update(editing.id, {
          name, description, parameters_schema: schema,
          code: code || undefined,
          requires_sandbox: requiresSandbox,
          requires_approval: requiresApproval,
        });
      } else {
        await api.tools.create({ name, description, parameters_schema: schema, code, requires_sandbox: requiresSandbox, requires_approval: requiresApproval });
      }
      resetForm(); await loadTools();
    } catch (e: any) { alert(e.message); }
    setSaving(false);
  };

  const handleToggle = async (t: ToolItem) => {
    await api.tools.update(t.id, { is_active: !t.is_active });
    await loadTools();
  };

  const handleDelete = async (t: ToolItem) => {
    if (t.is_builtin) return;
    if (confirm(`Delete tool "${t.name}"?`)) {
      await api.tools.delete(t.id); await loadTools();
    }
  };

  const handleUpload = async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const toolName = file.name.replace(/\.py$/, "").replace(/[^a-zA-Z0-9_]/g, "_");
    formData.append("name", toolName);
    formData.append("description", `Custom tool from ${file.name}`);
    const API_URL = typeof window !== "undefined"
      ? (window.location.port ? `http://${window.location.hostname}:8000` : window.location.origin)
      : "http://localhost:8000";
    const resp = await fetch(`${API_URL}/api/tools/upload`, { method: "POST", body: formData });
    if (resp.ok) { await loadTools(); } else { alert("Upload failed"); }
  };

  const builtinTools = tools.filter(t => t.is_builtin);
  const customTools = tools.filter(t => !t.is_builtin);

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-3 pt-14 md:p-6 md:pt-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Tools</h1>
              <p className="text-sm text-zinc-500 mt-1">Built-in and custom tools available to all agents</p>
            </div>
            <div className="flex gap-2">
              <label className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm transition-colors cursor-pointer">
                <Upload size={16} /> Upload .py
                <input type="file" accept=".py" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); e.target.value = ""; }} />
              </label>
              <button onClick={() => { resetForm(); setShowForm(true); }}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm transition-colors">
                <Plus size={16} /> New Tool
              </button>
            </div>
          </div>

          {/* Form */}
          {showForm && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">{editing ? `Edit: ${editing.name}` : "Create Custom Tool"}</h2>
                <button onClick={resetForm} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400"><X size={18} /></button>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-400">Name</label>
                  <input value={name} onChange={(e) => setName(e.target.value)}                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:opacity-50"
                    placeholder="my_custom_tool" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-400">Description</label>
                  <input value={description} onChange={(e) => setDescription(e.target.value)}                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:opacity-50"
                    placeholder="What does this tool do?" />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400">Parameters Schema (JSON)</label>
                <textarea value={paramsSchema} onChange={(e) => setParamsSchema(e.target.value)}                  rows={5}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs font-mono resize-none focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:opacity-50" />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-zinc-400">Python Code</label>
                  {editing?.is_builtin && !code && (
                    <button
                      onClick={async () => {
                        try {
                          const API_URL = typeof window !== "undefined"
                            ? (window.location.port ? `http://${window.location.hostname}:8000` : window.location.origin)
                            : "http://localhost:8000";
                          const resp = await fetch(`${API_URL}/api/tools/${editing.id}/source`);
                          if (resp.ok) {
                            const data = await resp.json();
                            setCode(data.source || "");
                          }
                        } catch {}
                      }}
                      className="text-xs text-violet-400 hover:text-violet-300 transition-colors"
                    >
                      Load built-in source
                    </button>
                  )}
                </div>
                {editing?.is_builtin && (
                  <div className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-[11px] font-mono text-zinc-500 mb-1">
                    Built-in: {editing.implementation}
                  </div>
                )}
                <textarea value={code} onChange={(e) => setCode(e.target.value)}
                  rows={12}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-xs font-mono resize-y focus:outline-none focus:ring-1 focus:ring-violet-500 text-emerald-300"
                  placeholder="def execute(**kwargs):&#10;    return 'result'" />
                <p className="text-[11px] text-zinc-600">
                  Define an <code className="text-zinc-400">execute(**kwargs)</code> function. Parameters from the schema are passed as kwargs. Return a string or dict.
                  {editing?.is_builtin && " For built-in tools, saving code here creates a custom override."}
                </p>
              </div>

              <div className="flex gap-4">
                <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
                  <input type="checkbox" checked={requiresApproval} onChange={(e) => setRequiresApproval(e.target.checked)} className="w-3.5 h-3.5 rounded" />
                  Requires approval
                </label>
                <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
                  <input type="checkbox" checked={requiresSandbox} onChange={(e) => setRequiresSandbox(e.target.checked)} className="w-3.5 h-3.5 rounded" />
                  Run in sandbox
                </label>
              </div>

              <div className="flex justify-end gap-2">
                <button onClick={resetForm} className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:bg-zinc-800">Cancel</button>
                <button onClick={handleSave} disabled={saving || !name}
                  className="px-4 py-2 rounded-lg text-sm bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 disabled:text-zinc-500">
                  {saving ? "Saving..." : editing ? "Update" : "Create"}
                </button>
              </div>
            </div>
          )}

          {/* Custom Tools */}
          {customTools.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">Custom Tools</h2>
              {customTools.map((t) => (
                <div key={t.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex items-center justify-between hover:border-zinc-700 transition-colors">
                  <div className="flex items-center gap-3">
                    <button onClick={() => handleToggle(t)} className="shrink-0">
                      {t.is_active ? <ToggleRight size={24} className="text-emerald-400" /> : <ToggleLeft size={24} className="text-zinc-600" />}
                    </button>
                    <div>
                      <div className="flex items-center gap-2">
                        <Code size={14} className="text-violet-400" />
                        <span className="text-sm font-medium font-mono">{t.name}</span>
                      </div>
                      <p className="text-[11px] text-zinc-500">{t.description}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button onClick={() => openEdit(t)} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300"><Pencil size={14} /></button>
                    <button onClick={() => handleDelete(t)} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-red-400"><Trash2 size={14} /></button>
                  </div>
                </div>
              ))}
            </section>
          )}

          {/* Built-in Tools */}
          <section className="space-y-2">
            <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">Built-in Tools ({builtinTools.length})</h2>
            {loading ? (
              <p className="text-sm text-zinc-500">Loading...</p>
            ) : (
              <div className="space-y-1">
                {builtinTools.map((t) => (
                  <div key={t.id} className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 flex items-center justify-between hover:border-zinc-700 transition-colors">
                    <div className="flex items-center gap-3">
                      <button onClick={() => handleToggle(t)} className="shrink-0">
                        {t.is_active ? <ToggleRight size={20} className="text-emerald-400" /> : <ToggleLeft size={20} className="text-zinc-600" />}
                      </button>
                      <div>
                        <div className="flex items-center gap-2">
                          <Wrench size={12} className="text-zinc-500" />
                          <span className="text-sm font-mono text-zinc-300">{t.name}</span>
                          {t.requires_approval && <span title="Requires approval"><ShieldCheck size={10} className="text-amber-400" /></span>}
                        </div>
                        <p className="text-[11px] text-zinc-500 truncate max-w-md">{t.description}</p>
                      </div>
                    </div>
                    <button onClick={() => openEdit(t)} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300"><Pencil size={14} /></button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
