"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAgentStore } from "@/stores/agentStore";
import { AgentCard } from "@/components/agents/AgentCard";
import { AgentForm } from "@/components/agents/AgentForm";
import { RunAgentDialog } from "@/components/agents/RunAgentDialog";
import { Sidebar } from "@/components/layout/Sidebar";
import { Plus, Layers } from "lucide-react";
import { api } from "@/lib/api-client";
import type { Agent } from "@/lib/types";

export default function AgentsPage() {
  const { agents, loading, editingAgent, loadAgents, createAgent, updateAgent, deleteAgent, setEditingAgent } =
    useAgentStore();
  const [showForm, setShowForm] = useState(false);
  const [runAgent, setRunAgent] = useState<Agent | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templates, setTemplates] = useState<any[]>([]);
  const router = useRouter();

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  const handleCreate = async (data: Partial<Agent>) => {
    await createAgent(data);
    setShowForm(false);
  };

  const handleUpdate = async (data: Partial<Agent>) => {
    if (editingAgent) {
      await updateAgent(editingAgent.id, data);
    }
  };

  const handleDelete = async (agent: Agent) => {
    if (confirm(`Delete agent "${agent.name}"?`)) {
      await deleteAgent(agent.id);
    }
  };

  const handleShowTemplates = async () => {
    const data = await api.templates.list();
    setTemplates(data.items);
    setShowTemplates(true);
  };

  const handleDeployTemplate = async (template: any) => {
    await createAgent(template.config);
    setShowTemplates(false);
  };

  const handleRunAgent = async (agent: Agent, instructions: string) => {
    await api.runs.create({
      agent_id: agent.id,
      instructions: instructions || undefined,
    });
    setRunAgent(null);
    router.push("/runs");
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-3 pt-14 md:p-6 md:pt-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Agents</h1>
              <p className="text-sm text-zinc-500 mt-1">
                Create and manage specialized AI agents
              </p>
            </div>
            <div className="flex gap-2">
              <button onClick={handleShowTemplates}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm transition-colors">
                <Layers size={16} /> From Template
              </button>
              <button
                onClick={() => { setEditingAgent(null); setShowForm(true); }}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm transition-colors">
                <Plus size={16} /> New Agent
              </button>
            </div>
          </div>

          {(showForm || editingAgent) && (
            <AgentForm
              agent={editingAgent}
              onSave={editingAgent ? handleUpdate : handleCreate}
              onCancel={() => {
                setShowForm(false);
                setEditingAgent(null);
              }}
              onDone={() => loadAgents()}
            />
          )}

          {loading ? (
            <p className="text-sm text-zinc-500">Loading agents...</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {agents.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  onEdit={(a) => {
                    setShowForm(false);
                    setEditingAgent(a);
                  }}
                  onDelete={handleDelete}
                  onRun={setRunAgent}
                />
              ))}
            </div>
          )}
        </div>
      </main>

      {showTemplates && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-lg mx-4 shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
              <h2 className="text-sm font-semibold">Deploy from Template</h2>
              <button onClick={() => setShowTemplates(false)} className="text-zinc-400 hover:text-zinc-200 text-sm">Cancel</button>
            </div>
            <div className="p-4 space-y-2 max-h-96 overflow-y-auto">
              {templates.map((t) => (
                <button key={t.id} onClick={() => handleDeployTemplate(t)}
                  className="w-full text-left bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg p-3 transition-colors">
                  <div className="text-sm font-medium">{t.name}</div>
                  <div className="text-xs text-zinc-400 mt-0.5">{t.description}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {runAgent && (
        <RunAgentDialog
          agent={runAgent}
          onRun={handleRunAgent}
          onClose={() => setRunAgent(null)}
        />
      )}
    </div>
  );
}
