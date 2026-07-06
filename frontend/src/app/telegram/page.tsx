"use client";

import { useEffect, useState, useCallback } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { api } from "@/lib/api-client";
import {
  Plus, Trash2, Send, ToggleLeft, ToggleRight, X, Clock, Check, CheckCircle, XCircle, ShieldAlert, DollarSign,
} from "lucide-react";

interface TelegramUser {
  id: string;
  telegram_id: string;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  note: string | null;
  status: "pending" | "active" | "blocked";
  can_chat: boolean;
  can_receive: boolean;
  can_approve: boolean;
  daily_budget_usd: number | null;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

const STATUS_CONFIG = {
  pending: { icon: Clock, color: "text-amber-400", bg: "bg-amber-950/30", label: "Pending" },
  active: { icon: CheckCircle, color: "text-emerald-400", bg: "bg-emerald-950/30", label: "Active" },
  blocked: { icon: XCircle, color: "text-red-400", bg: "bg-red-950/30", label: "Blocked" },
};

function StatusBadge({ status }: { status: TelegramUser["status"] }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${cfg.color} ${cfg.bg} border border-current/20`}>
      <Icon size={12} />
      {cfg.label}
    </span>
  );
}

function getTimeAgo(date: Date): string {
  const s = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function displayName(u: TelegramUser): string {
  const name = [u.first_name, u.last_name].filter(Boolean).join(" ");
  return name || u.username || u.telegram_id;
}

const isValidTelegramId = (v: string) => /^-?\d+$/.test(v.trim());

export default function TelegramPage() {
  const [users, setUsers] = useState<TelegramUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingBudgetId, setEditingBudgetId] = useState<string | null>(null);
  const [budgetDraft, setBudgetDraft] = useState("");

  const [telegramId, setTelegramId] = useState("");
  const [note, setNote] = useState("");
  const [canChat, setCanChat] = useState(true);
  const [canReceive, setCanReceive] = useState(true);
  const [canApprove, setCanApprove] = useState(false);
  const [budget, setBudget] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api.telegramUsers.list();
      setUsers(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load Telegram users");
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  // Per-row mutation wrapper: clears the last error, blocks concurrent edits on the
  // same row, surfaces failures in the page-level callout, and refreshes the list.
  const mutate = async (id: string, fn: () => Promise<void>) => {
    if (busyId) return;
    setBusyId(id); setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusyId(null);
  };

  const resetForm = () => {
    setTelegramId(""); setNote(""); setCanChat(true); setCanReceive(true);
    setCanApprove(false); setBudget(""); setShowForm(false);
  };

  const handleAdd = async () => {
    setSaving(true); setError(null);
    try {
      await api.telegramUsers.create({
        telegram_id: telegramId.trim(),
        note: note || null,
        status: "active",
        can_chat: canChat,
        can_receive: canReceive,
        can_approve: canApprove,
        daily_budget_usd: budget === "" ? null : Number(budget),
      });
      resetForm(); await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setSaving(false);
  };

  const handleToggle = (u: TelegramUser, field: "can_chat" | "can_receive" | "can_approve") =>
    mutate(u.id, () => api.telegramUsers.update(u.id, { [field]: !u[field] }));

  const handleApprove = (u: TelegramUser) =>
    mutate(u.id, () => api.telegramUsers.update(u.id, { status: "active", can_chat: true, can_receive: true }));

  // Unblocking is not re-approval: the id returns to pending for an explicit Approve.
  const handleBlock = (u: TelegramUser) =>
    mutate(u.id, () => api.telegramUsers.update(u.id, { status: u.status === "blocked" ? "pending" : "blocked" }));

  const handleDelete = (u: TelegramUser) => {
    if (confirm(`Remove Telegram ID ${u.telegram_id} (${displayName(u)})?`)) {
      mutate(u.id, () => api.telegramUsers.delete(u.id));
    }
  };

  const openBudgetEdit = (u: TelegramUser) => {
    setEditingBudgetId(u.id);
    setBudgetDraft(u.daily_budget_usd != null ? String(u.daily_budget_usd) : "");
  };

  const saveBudget = async (u: TelegramUser) => {
    const trimmed = budgetDraft.trim();
    let value: number | null = null;
    if (trimmed !== "") {
      const n = Number(trimmed);
      if (!Number.isFinite(n) || n < 0) {
        setError("Daily budget must be a non-negative number.");
        return;
      }
      value = n;
    }
    await mutate(u.id, async () => {
      await api.telegramUsers.update(u.id, { daily_budget_usd: value });
      setEditingBudgetId(null);
    });
  };

  const pending = users.filter((u) => u.status === "pending");
  const listed = users.filter((u) => u.status !== "pending");

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-3 pt-14 md:p-6 md:pt-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Telegram Access</h1>
              <p className="text-sm text-zinc-500 mt-1">Control who can talk to Gini on Telegram</p>
            </div>
            <button onClick={() => { resetForm(); setShowForm(true); }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm transition-colors">
              <Plus size={16} /> Add ID
            </button>
          </div>

          {error && (
            <div className="flex items-start justify-between gap-2 rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-[11px] text-red-300">
              <span>{error}</span>
              <button onClick={() => setError(null)} className="shrink-0 hover:text-red-100" aria-label="Dismiss error">
                <X size={12} />
              </button>
            </div>
          )}

          {showForm && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Add Telegram ID</h2>
                <button onClick={resetForm} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400"><X size={18} /></button>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-400">Telegram ID</label>
                  <input value={telegramId} onChange={(e) => setTelegramId(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-violet-500"
                    placeholder="e.g. 123456789 (groups start with -)" />
                  {telegramId && !isValidTelegramId(telegramId) && (
                    <p className="text-[11px] text-red-400">Must be digits, with an optional leading minus.</p>
                  )}
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-400">Note (optional)</label>
                  <input value={note} onChange={(e) => setNote(e.target.value)}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
                    placeholder="e.g. Mom's phone" />
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-4">
                <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
                  <input type="checkbox" checked={canChat} onChange={(e) => setCanChat(e.target.checked)} className="w-3.5 h-3.5 rounded" />
                  Can chat
                </label>
                <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
                  <input type="checkbox" checked={canReceive} onChange={(e) => setCanReceive(e.target.checked)} className="w-3.5 h-3.5 rounded" />
                  Can receive messages
                </label>
                <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
                  <input type="checkbox" checked={canApprove} onChange={(e) => setCanApprove(e.target.checked)} className="w-3.5 h-3.5 rounded" />
                  Can approve tool calls
                </label>
                <div className="flex items-center gap-2">
                  <label className="text-xs font-medium text-zinc-400">Daily budget $</label>
                  <input type="number" min="0" step="0.5" value={budget} onChange={(e) => setBudget(e.target.value)}
                    className="w-24 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
                    placeholder="none" />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <button onClick={resetForm} className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:bg-zinc-800">Cancel</button>
                <button onClick={handleAdd} disabled={saving || !isValidTelegramId(telegramId)}
                  className="px-4 py-2 rounded-lg text-sm bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 disabled:text-zinc-500">
                  {saving ? "Saving..." : "Add"}
                </button>
              </div>
            </div>
          )}

          {pending.length > 0 && (
            <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 p-4 space-y-3">
              <div className="flex items-start gap-2 text-xs text-amber-300/90">
                <ShieldAlert size={14} className="mt-0.5 shrink-0" />
                <span>
                  {pending.length} pending {pending.length === 1 ? "request" : "requests"} — these people messaged
                  Gini on Telegram but aren&apos;t approved yet.
                </span>
              </div>
              {pending.map((u) => (
                <div key={u.id} className="flex items-center justify-between gap-3 rounded-lg bg-zinc-900/60 px-3 py-2">
                  <div className="min-w-0">
                    <span className="text-sm text-zinc-200">{displayName(u)}</span>
                    {u.username && <span className="text-xs text-zinc-500 ml-2">@{u.username}</span>}
                    <div className="text-[11px] text-zinc-500 font-mono">
                      {u.telegram_id}
                      {u.last_seen_at && <span className="font-sans"> · seen {getTimeAgo(new Date(u.last_seen_at))}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button onClick={() => handleApprove(u)} disabled={busyId === u.id}
                      className="px-3 py-1.5 rounded-lg text-xs bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 transition-colors">
                      Approve
                    </button>
                    <button onClick={() => handleBlock(u)} disabled={busyId === u.id}
                      className="px-3 py-1.5 rounded-lg text-xs bg-zinc-800 hover:bg-red-900/60 text-zinc-300 disabled:opacity-50 transition-colors">
                      Block
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {loading ? (
            <p className="text-sm text-zinc-500">Loading Telegram users...</p>
          ) : users.length === 0 ? (
            <div className="text-center py-12 text-zinc-500">
              <Send size={32} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm">No Telegram IDs yet. Add one, or wait for someone to message the bot.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {listed.map((u) => (
                <div key={u.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-2 hover:border-zinc-700 transition-colors">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-sm font-medium ${u.status === "blocked" ? "text-zinc-500" : "text-zinc-100"}`}>
                          {displayName(u)}
                        </span>
                        {u.username && <span className="text-xs text-zinc-500">@{u.username}</span>}
                        <StatusBadge status={u.status} />
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-zinc-500 mt-0.5">
                        <code className="bg-zinc-800 rounded px-1.5 py-0.5 font-mono">{u.telegram_id}</code>
                        {u.last_seen_at ? <span>seen {getTimeAgo(new Date(u.last_seen_at))}</span> : <span>never seen</span>}
                        {u.note && <span className="truncate">· {u.note}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {editingBudgetId === u.id ? (
                        <div className="flex items-center gap-1">
                          <input
                            type="number" min="0" step="0.5" autoFocus value={budgetDraft}
                            onChange={(e) => setBudgetDraft(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") saveBudget(u); if (e.key === "Escape") setEditingBudgetId(null); }}
                            className="w-20 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500"
                            placeholder="no limit"
                          />
                          <button onClick={() => saveBudget(u)} disabled={busyId === u.id}
                            className="p-1 rounded-lg hover:bg-zinc-800 text-emerald-400 disabled:opacity-50" title="Save budget">
                            <Check size={14} />
                          </button>
                          <button onClick={() => setEditingBudgetId(null)}
                            className="p-1 rounded-lg hover:bg-zinc-800 text-zinc-500" title="Cancel">
                            <X size={14} />
                          </button>
                        </div>
                      ) : (
                        <button onClick={() => openBudgetEdit(u)}
                          className="flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-zinc-800 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
                          title="Daily budget (blank = unlimited)">
                          <DollarSign size={11} />
                          {u.daily_budget_usd != null ? `${u.daily_budget_usd.toFixed(2)}/day` : "no limit"}
                        </button>
                      )}
                      <button onClick={() => handleBlock(u)} disabled={busyId === u.id}
                        className="px-2 py-1 rounded-lg hover:bg-zinc-800 text-[11px] text-zinc-500 hover:text-amber-400 disabled:opacity-50 transition-colors">
                        {u.status === "blocked" ? "Unblock" : "Block"}
                      </button>
                      <button onClick={() => handleDelete(u)} disabled={busyId === u.id}
                        className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-red-400 disabled:opacity-50 transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 pt-1 border-t border-zinc-800/70">
                    <button onClick={() => handleToggle(u, "can_chat")} disabled={busyId === u.id}
                      className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-50 transition-colors">
                      {u.can_chat ? <ToggleRight size={20} className="text-emerald-400" /> : <ToggleLeft size={20} className="text-zinc-600" />}
                      Chat
                    </button>
                    <button onClick={() => handleToggle(u, "can_receive")} disabled={busyId === u.id}
                      className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-50 transition-colors">
                      {u.can_receive ? <ToggleRight size={20} className="text-emerald-400" /> : <ToggleLeft size={20} className="text-zinc-600" />}
                      Receive
                    </button>
                    <button onClick={() => handleToggle(u, "can_approve")} disabled={busyId === u.id}
                      className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-50 transition-colors">
                      {u.can_approve ? <ToggleRight size={20} className="text-violet-400" /> : <ToggleLeft size={20} className="text-zinc-600" />}
                      Approve
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
