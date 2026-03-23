"use client";

import { useEffect, useState, useCallback } from "react";
import { Brain, Search, Plus, Trash2, X, Upload } from "lucide-react";
import { api } from "@/lib/api-client";

interface Memory {
  id: string;
  content: string;
  summary: string | null;
  source: string;
  agent_id: string | null;
  similarity?: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export default function MemoriesPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async (q?: string) => {
    setLoading(true);
    try {
      const data = await api.memories.list(q ? { q, limit: 50 } : { limit: 50 });
      setMemories(data.items);
      setTotal(data.total);
    } catch {
      // ignore
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSearch = () => {
    load(searchQuery || undefined);
  };

  const handleCreate = async () => {
    if (!newContent.trim()) return;
    setCreating(true);
    try {
      await api.memories.create({ content: newContent.trim(), source: "manual" });
      setNewContent("");
      setShowCreate(false);
      load();
    } catch {
      // ignore
    }
    setCreating(false);
  };

  const handleDelete = async (id: string) => {
    try {
      await api.memories.delete(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
      setTotal((prev) => prev - 1);
    } catch {
      // ignore
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto">
      <div className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain size={18} className="text-zinc-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Memories</h1>
          <span className="text-xs text-zinc-500 ml-2">{total} stored</span>
        </div>
        <div className="flex gap-2">
          <label className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg transition-colors cursor-pointer">
            <Upload size={12} />
            Upload File
            <input type="file" className="hidden" accept=".txt,.md,.csv,.json"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                const formData = new FormData();
                formData.append("file", file);
                formData.append("source", "document");
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/memories/upload`, {
                  method: "POST", body: formData,
                });
                if (res.ok) {
                  const data = await res.json();
                  alert(`Uploaded: ${data.chunks} chunks from ${data.filename}`);
                  load();
                }
                e.target.value = "";
              }}
            />
          </label>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-violet-600 hover:bg-violet-500 text-white rounded-lg transition-colors"
          >
            <Plus size={12} />
            Add Memory
          </button>
        </div>
      </div>

      <div className="p-3 pt-14 md:p-6 md:pt-6 space-y-4 max-w-4xl mx-auto w-full">
        {/* Search Bar */}
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Semantic search across memories..."
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-9 pr-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-700"
            />
          </div>
          <button
            onClick={handleSearch}
            className="px-4 py-2 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg transition-colors"
          >
            Search
          </button>
          {searchQuery && (
            <button
              onClick={() => { setSearchQuery(""); load(); }}
              className="px-3 py-2 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Create Form */}
        {showCreate && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
            <textarea
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              placeholder="Enter a memory to store (e.g., 'The user prefers Python over JavaScript')..."
              rows={3}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-700 resize-none"
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowCreate(false)}
                className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={creating || !newContent.trim()}
                className="px-4 py-1.5 text-xs bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white rounded-lg transition-colors"
              >
                {creating ? "Storing..." : "Store Memory"}
              </button>
            </div>
          </div>
        )}

        {/* Memory List */}
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 h-24 animate-pulse" />
            ))}
          </div>
        ) : memories.length === 0 ? (
          <div className="text-center py-16 text-zinc-500">
            <Brain size={32} className="mx-auto mb-3 opacity-50" />
            <p className="text-sm">
              {searchQuery ? "No memories match your search" : "No memories stored yet"}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {memories.map((m) => (
              <div
                key={m.id}
                className="group rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 hover:border-zinc-700 transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-zinc-200 whitespace-pre-wrap">{m.content}</p>
                    <div className="flex items-center gap-3 mt-2 text-[11px] text-zinc-500">
                      <span className="bg-zinc-800 rounded px-1.5 py-0.5">{m.source}</span>
                      {m.similarity != null && (
                        <span className="text-violet-400">{(m.similarity * 100).toFixed(0)}% match</span>
                      )}
                      <span>{new Date(m.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(m.id)}
                    className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 transition-all shrink-0"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
