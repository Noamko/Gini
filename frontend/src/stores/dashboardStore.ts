"use client";

import { create } from "zustand";
import { api } from "@/lib/api-client";
import { WSClient } from "@/lib/ws-client";

export interface AgentState {
  id: string;
  name: string;
  description: string | null;
  state: string;
  is_main: boolean;
  llm_provider: string;
  llm_model: string;
}

export interface CostSummary {
  total_messages: number;
  total_tokens: number;
  total_cost: number;
}

export interface DashboardEvent {
  id: string;
  event_type: string;
  source: string;
  status: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface CostBreakdownRow {
  group: string;
  count: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_ms: number;
}

interface DashboardState {
  agents: AgentState[];
  costs: CostSummary | null;
  events: DashboardEvent[];
  costBreakdown: CostBreakdownRow[];
  connected: boolean;
  wsClient: WSClient | null;

  loadAgents: () => Promise<void>;
  loadCosts: () => Promise<void>;
  loadEvents: () => Promise<void>;
  loadCostBreakdown: (groupBy?: string) => Promise<void>;
  connectWS: () => void;
  disconnectWS: () => void;
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  agents: [],
  costs: null,
  events: [],
  costBreakdown: [],
  connected: false,
  wsClient: null,

  loadAgents: async () => {
    const agents = await api.dashboard.agents();
    set({ agents });
  },

  loadCosts: async () => {
    const costs = await api.dashboard.costs();
    set({ costs });
  },

  loadEvents: async () => {
    const events = await api.dashboard.events();
    set({ events });
  },

  loadCostBreakdown: async (groupBy = "model") => {
    try {
      const breakdown = await api.traces.breakdown(groupBy);
      set({ costBreakdown: breakdown });
    } catch {
      // traces table may be empty
    }
  },

  connectWS: () => {
    const existing = get().wsClient;
    if (existing) return;

    const client = new WSClient("/ws/dashboard");

    client.onMessage((data) => {
      if (data.type === "initial_state") {
        // Merge live states into agents
        const liveStates: Record<string, any> = data.agent_states || {};
        set((s) => ({
          agents: s.agents.map((a) => ({
            ...a,
            state: liveStates[a.id]?.state || a.state,
          })),
        }));
      } else if (data.type === "agent_state_change") {
        set((s) => ({
          agents: s.agents.map((a) =>
            a.id === data.agent_id ? { ...a, state: data.state } : a
          ),
        }));
      } else if (data.type === "delegation_event" || data.type === "event") {
        // Prepend new event
        const newEvent: DashboardEvent = {
          id: data.id || crypto.randomUUID(),
          event_type: data.event_type || data.type,
          source: data.source || "system",
          status: data.status || "completed",
          payload: data.payload || data,
          created_at: data.created_at || new Date().toISOString(),
        };
        set((s) => ({
          events: [newEvent, ...s.events].slice(0, 50),
        }));
      }
    });

    client.connect();
    set({ wsClient: client, connected: true });
  },

  disconnectWS: () => {
    const client = get().wsClient;
    if (client) {
      client.disconnect();
      set({ wsClient: null, connected: false });
    }
  },
}));
