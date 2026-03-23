"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAgentStore } from "@/stores/agentStore";
import { AgentCard } from "@/components/agents/AgentCard";
import { AgentForm } from "@/components/agents/AgentForm";
import { RunAgentDialog } from "@/components/agents/RunAgentDialog";
import { Sidebar } from "@/components/layout/Sidebar";
import { Plus } from "lucide-react";
import { api } from "@/lib/api-client";
import type { Agent } from "@/lib/types";

export default function AgentsPage() {
  const { agents, loading, editingAgent, loadAgents, createAgent, updateAgent, deleteAgent, setEditingAgent } =
    useAgentStore();
  const [showForm, setShowForm] = useState(false);
  const [runAgent, setRunAgent] = useState<Agent | null>(null);
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
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Agents</h1>
              <p className="text-sm text-zinc-500 mt-1">
                Create and manage specialized AI agents
              </p>
            </div>
            <button
              onClick={() => {
                setEditingAgent(null);
                setShowForm(true);
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm transition-colors"
            >
              <Plus size={16} />
              New Agent
            </button>
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
