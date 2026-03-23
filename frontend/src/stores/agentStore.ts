"use client";

import { create } from "zustand";
import type { Agent } from "@/lib/types";
import { api } from "@/lib/api-client";

interface AgentState {
  agents: Agent[];
  loading: boolean;
  editingAgent: Agent | null;

  loadAgents: () => Promise<void>;
  createAgent: (data: Partial<Agent>) => Promise<Agent>;
  updateAgent: (id: string, data: Partial<Agent>) => Promise<Agent>;
  deleteAgent: (id: string) => Promise<void>;
  setEditingAgent: (agent: Agent | null) => void;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  agents: [],
  loading: false,
  editingAgent: null,

  loadAgents: async () => {
    set({ loading: true });
    try {
      const data = await api.agents.list();
      set({ agents: data.items, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  createAgent: async (data) => {
    const agent = await api.agents.create(data);
    set((s) => ({ agents: [...s.agents, agent] }));
    return agent;
  },

  updateAgent: async (id, data) => {
    const agent = await api.agents.update(id, data);
    set((s) => ({
      agents: s.agents.map((a) => (a.id === id ? agent : a)),
      editingAgent: null,
    }));
    return agent;
  },

  deleteAgent: async (id) => {
    await api.agents.delete(id);
    set((s) => ({
      agents: s.agents.filter((a) => a.id !== id),
      editingAgent: s.editingAgent?.id === id ? null : s.editingAgent,
    }));
  },

  setEditingAgent: (agent) => set({ editingAgent: agent }),
}));
