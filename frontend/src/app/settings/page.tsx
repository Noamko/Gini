"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { api } from "@/lib/api-client";
import { Plus, Pencil, Trash2, KeyRound, Eye, EyeOff, Settings, CheckCircle, XCircle, Save, RefreshCw, Download, Upload } from "lucide-react";

interface Credential {
  id: string;
  name: string;
  description: string | null;
  credential_type: string;
  is_active: boolean;
}

interface AppSettings {
  app_name: string;
  app_version: string;
  debug: boolean;
  default_llm_provider: string;
  default_llm_model: string;
  default_temperature: number;
  default_max_tokens: number;
  has_openai_key: boolean;
  has_anthropic_key: boolean;
}

interface ModelOption {
  id: string;
  name: string;
  provider: string;
}

export default function SettingsPage() {
  // App settings
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null);
  const [editProvider, setEditProvider] = useState("");
  const [editModel, setEditModel] = useState("");
  const [editTemp, setEditTemp] = useState("");
  const [editMaxTokens, setEditMaxTokens] = useState("");
  const [saving, setSaving] = useState(false);

  // Models
  const [models, setModels] = useState<ModelOption[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);

  // Credentials
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Credential | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [credType, setCredType] = useState("api_key");
  const [value, setValue] = useState("");
  const [showValue, setShowValue] = useState(false);

  const loadSettings = useCallback(async () => {
    try {
      const s = await api.settings.get();
      setAppSettings(s);
      setEditProvider(s.default_llm_provider);
      setEditModel(s.default_llm_model);
      setEditTemp(String(s.default_temperature));
      setEditMaxTokens(String(s.default_max_tokens));
    } catch {}
  }, []);

  const loadModels = useCallback(async (refresh = false) => {
    setLoadingModels(true);
    try {
      const data = await api.models.list(refresh);
      setModels(data.models);
    } catch {}
    setLoadingModels(false);
  }, []);

  const filteredModels = useMemo(
    () => models.filter((m) => m.provider === editProvider),
    [models, editProvider]
  );

  const loadCredentials = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.credentials.list();
      setCredentials(data);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    loadSettings();
    loadModels();
    loadCredentials();
  }, [loadSettings, loadModels, loadCredentials]);

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      const updated = await api.settings.update({
        default_llm_provider: editProvider,
        default_llm_model: editModel,
        default_temperature: parseFloat(editTemp),
        default_max_tokens: parseInt(editMaxTokens),
      });
      setAppSettings(updated);
    } catch {}
    setSaving(false);
  };

  const resetForm = () => {
    setName(""); setDescription(""); setCredType("api_key"); setValue("");
    setShowValue(false); setEditing(null); setShowForm(false);
  };

  const openEdit = (cred: Credential) => {
    setName(cred.name); setDescription(cred.description || "");
    setCredType(cred.credential_type); setValue(""); setEditing(cred); setShowForm(true);
  };

  const handleSaveCred = async () => {
    if (editing) {
      const data: Record<string, unknown> = { name, description: description || null, credential_type: credType };
      if (value) data.value = value;
      await api.credentials.update(editing.id, data);
    } else {
      await api.credentials.create({ name, description: description || null, credential_type: credType, value });
    }
    resetForm(); loadCredentials();
  };

  const handleDeleteCred = async (cred: Credential) => {
    if (!confirm(`Delete credential "${cred.name}"?`)) return;
    await api.credentials.delete(cred.id); loadCredentials();
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="border-b border-zinc-800 px-6 py-4">
          <div className="flex items-center gap-2">
            <Settings size={18} className="text-zinc-400" />
            <h1 className="text-lg font-semibold text-zinc-100">Settings</h1>
          </div>
        </div>

        <div className="p-3 pt-14 md:p-6 md:pt-6 max-w-4xl mx-auto space-y-8">
          {/* App Configuration */}
          <section className="space-y-4">
            <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">LLM Defaults</h2>

            {appSettings && (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
                {/* API Key Status */}
                <div className="flex gap-4 text-xs mb-2">
                  <span className="flex items-center gap-1.5">
                    {appSettings.has_anthropic_key
                      ? <CheckCircle size={12} className="text-emerald-400" />
                      : <XCircle size={12} className="text-red-400" />}
                    Anthropic
                  </span>
                  <span className="flex items-center gap-1.5">
                    {appSettings.has_openai_key
                      ? <CheckCircle size={12} className="text-emerald-400" />
                      : <XCircle size={12} className="text-red-400" />}
                    OpenAI
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-zinc-500 mb-1">Provider</label>
                    <select
                      value={editProvider}
                      onChange={(e) => setEditProvider(e.target.value)}
                      className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                    >
                      <option value="anthropic">Anthropic</option>
                      <option value="openai">OpenAI</option>
                    </select>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-xs text-zinc-500">Model</label>
                      <button
                        onClick={() => loadModels(true)}
                        disabled={loadingModels}
                        className="text-xs text-zinc-500 hover:text-zinc-300 flex items-center gap-1 transition-colors"
                      >
                        <RefreshCw size={10} className={loadingModels ? "animate-spin" : ""} />
                        Refresh
                      </button>
                    </div>
                    <select
                      value={editModel}
                      onChange={(e) => setEditModel(e.target.value)}
                      className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-violet-500 font-mono"
                    >
                      {filteredModels.length === 0 && (
                        <option value={editModel}>{editModel || "No models available"}</option>
                      )}
                      {filteredModels.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-500 mb-1">Temperature</label>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      max="2"
                      value={editTemp}
                      onChange={(e) => setEditTemp(e.target.value)}
                      className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-500 mb-1">Max Tokens</label>
                    <input
                      type="number"
                      step="256"
                      min="256"
                      max="32000"
                      value={editMaxTokens}
                      onChange={(e) => setEditMaxTokens(e.target.value)}
                      className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
                    />
                  </div>
                </div>

                <button
                  onClick={handleSaveSettings}
                  disabled={saving}
                  className="flex items-center gap-2 px-4 py-2 text-sm bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-lg transition-colors"
                >
                  <Save size={14} />
                  {saving ? "Saving..." : "Save Defaults"}
                </button>
              </div>
            )}
          </section>

          {/* Credential Vault */}
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">Credential Vault</h2>
                <p className="text-xs text-zinc-600 mt-1">Encrypted credentials for skills. Values are never exposed.</p>
              </div>
              <button
                onClick={() => { resetForm(); setShowForm(true); }}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs transition-colors"
              >
                <Plus size={14} />
                Add
              </button>
            </div>

            {showForm && (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-zinc-500 mb-1">Name</label>
                    <input value={name} onChange={(e) => setName(e.target.value)}
                      className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                      placeholder="e.g. GitHub Token" />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-500 mb-1">Type</label>
                    <select value={credType} onChange={(e) => setCredType(e.target.value)}
                      className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-emerald-500">
                      <option value="api_key">API Key</option>
                      <option value="token">Token</option>
                      <option value="password">Password</option>
                      <option value="oauth">OAuth</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Description</label>
                  <input value={description} onChange={(e) => setDescription(e.target.value)}
                    className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                    placeholder="What is this credential for?" />
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">
                    {editing ? "Value (blank to keep current)" : "Value"}
                  </label>
                  <div className="relative">
                    <input type={showValue ? "text" : "password"} value={value}
                      onChange={(e) => setValue(e.target.value)}
                      className="w-full rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-2 pr-10 text-sm focus:outline-none focus:border-emerald-500 font-mono"
                      placeholder={editing ? "••••••••" : "Enter secret value"} />
                    <button type="button" onClick={async () => {
                      if (!showValue && editing && !value) {
                        try {
                          const data = await api.credentials.reveal(editing.id);
                          setValue(data.value);
                        } catch {}
                      }
                      setShowValue(!showValue);
                    }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300">
                      {showValue ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSaveCred} disabled={!name.trim() || (!editing && !value.trim())}
                    className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-sm disabled:opacity-50 transition-colors">
                    {editing ? "Update" : "Create"}
                  </button>
                  <button onClick={resetForm}
                    className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm transition-colors">
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {loading ? (
              <div className="space-y-2">
                {[1, 2].map((i) => (
                  <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 h-16 animate-pulse" />
                ))}
              </div>
            ) : credentials.length === 0 ? (
              <div className="text-center py-12 text-zinc-500">
                <KeyRound size={28} className="mx-auto mb-2 opacity-50" />
                <p className="text-sm">No credentials stored</p>
              </div>
            ) : (
              <div className="space-y-2">
                {credentials.map((cred) => (
                  <div key={cred.id}
                    className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-900/50 px-4 py-3">
                    <div className="flex items-center gap-3">
                      <KeyRound size={14} className="text-emerald-400" />
                      <div>
                        <p className="text-sm font-medium">{cred.name}</p>
                        <p className="text-[11px] text-zinc-500">
                          {cred.credential_type}{cred.description && ` — ${cred.description}`}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className={`text-[11px] mr-2 ${cred.is_active ? "text-emerald-400" : "text-zinc-600"}`}>
                        {cred.is_active ? "Active" : "Inactive"}
                      </span>
                      <button onClick={() => openEdit(cred)}
                        className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => handleDeleteCred(cred)}
                        className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-red-400 transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Backup & Restore */}
          <section className="space-y-4">
            <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">Backup & Restore</h2>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
              <p className="text-xs text-zinc-500">
                Export all agents, skills, credentials, workflows, schedules, and webhooks as a JSON file.
                Restore imports everything back, matching by name (upsert).
              </p>
              <div className="flex gap-3">
                <button
                  onClick={async () => {
                    try {
                      const data = await api.backup.export();
                      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `gini-backup-${new Date().toISOString().slice(0, 10)}.json`;
                      a.click();
                      URL.revokeObjectURL(url);
                    } catch (e: any) {
                      alert(`Export failed: ${e.message}`);
                    }
                  }}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm transition-colors"
                >
                  <Download size={14} />
                  Export Backup
                </button>
                <label className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm transition-colors cursor-pointer">
                  <Upload size={14} />
                  Restore from File
                  <input
                    type="file"
                    accept=".json"
                    className="hidden"
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      if (!confirm("This will import/overwrite config data. Continue?")) {
                        e.target.value = "";
                        return;
                      }
                      try {
                        const text = await file.text();
                        const data = JSON.parse(text);
                        const result = await api.backup.restore(data);
                        alert(`Restore complete!\n${JSON.stringify(result.counts, null, 2)}`);
                        window.location.reload();
                      } catch (err: any) {
                        alert(`Restore failed: ${err.message}`);
                      }
                      e.target.value = "";
                    }}
                  />
                </label>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
