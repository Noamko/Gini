const API_URL = process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined"
    ? window.location.port
      ? `http://${window.location.hostname}:8000`
      : `${window.location.origin}`
    : "http://localhost:8000");

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.message || JSON.stringify(body);
    } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  agents: {
    list: (offset = 0, limit = 50) =>
      request<{ items: any[]; total: number }>(`/api/agents?offset=${offset}&limit=${limit}`),
    create: (data: any) =>
      request<any>("/api/agents", { method: "POST", body: JSON.stringify(data) }),
    get: (id: string) => request<any>(`/api/agents/${id}`),
    update: (id: string, data: any) =>
      request<any>(`/api/agents/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
      request<void>(`/api/agents/${id}`, { method: "DELETE" }),
    skills: (id: string) => request<any[]>(`/api/agents/${id}/skills`),
  },
  skills: {
    list: () => request<any[]>("/api/skills"),
    get: (id: string) => request<any>(`/api/skills/${id}`),
    create: (data: any) =>
      request<any>("/api/skills", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: any) =>
      request<any>(`/api/skills/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
      request<void>(`/api/skills/${id}`, { method: "DELETE" }),
    assign: (skillId: string, agentId: string) =>
      request<any>(`/api/skills/${skillId}/assign/${agentId}`, { method: "POST" }),
    unassign: (skillId: string, agentId: string) =>
      request<any>(`/api/skills/${skillId}/assign/${agentId}`, { method: "DELETE" }),
  },
  credentials: {
    list: () => request<any[]>("/api/credentials"),
    get: (id: string) => request<any>(`/api/credentials/${id}`),
    create: (data: any) =>
      request<any>("/api/credentials", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: any) =>
      request<any>(`/api/credentials/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
      request<void>(`/api/credentials/${id}`, { method: "DELETE" }),
    reveal: (id: string) => request<{ value: string }>(`/api/credentials/${id}/reveal`),
  },
  tools: {
    list: async () => {
      const data = await request<{ items: any[] }>("/api/tools");
      return data.items;
    },
  },
  traces: {
    list: (params?: { conversation_id?: string; agent_name?: string; offset?: number; limit?: number }) => {
      const sp = new URLSearchParams();
      if (params?.conversation_id) sp.set("conversation_id", params.conversation_id);
      if (params?.agent_name) sp.set("agent_name", params.agent_name);
      if (params?.offset) sp.set("offset", String(params.offset));
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return request<{ items: any[]; total: number }>(`/api/traces${qs ? `?${qs}` : ""}`);
    },
    get: (traceId: string) => request<any>(`/api/traces/${traceId}`),
    costs: () => request<any>("/api/costs"),
    breakdown: (groupBy: string = "model") =>
      request<any[]>(`/api/costs/breakdown?group_by=${groupBy}`),
  },
  dashboard: {
    agents: () => request<any[]>("/api/dashboard/agents"),
    costs: () => request<any>("/api/dashboard/costs"),
    events: (limit = 20) => request<any[]>(`/api/dashboard/events?limit=${limit}`),
  },
  settings: {
    get: () => request<any>("/api/settings"),
    update: (data: any) =>
      request<any>("/api/settings", { method: "PUT", body: JSON.stringify(data) }),
  },
  models: {
    list: (refresh = false) =>
      request<{ models: { id: string; name: string; provider: string }[] }>(
        `/api/models${refresh ? "?refresh=true" : ""}`
      ),
  },
  backup: {
    export: () => request<any>("/api/backup/export"),
    restore: (data: any) =>
      request<any>("/api/backup/restore", { method: "POST", body: JSON.stringify(data) }),
  },
  templates: {
    list: () => request<{ items: any[] }>("/api/templates"),
  },
  workflows: {
    list: () => request<{ items: any[] }>("/api/workflows"),
    get: (id: string) => request<any>(`/api/workflows/${id}`),
    create: (data: any) =>
      request<any>("/api/workflows", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: any) =>
      request<any>(`/api/workflows/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
      request<void>(`/api/workflows/${id}`, { method: "DELETE" }),
    run: (id: string) =>
      request<any>(`/api/workflows/${id}/run`, { method: "POST" }),
  },
  webhooks: {
    list: () => request<{ items: any[] }>("/api/webhooks"),
    get: (id: string) => request<any>(`/api/webhooks/${id}`),
    create: (data: any) =>
      request<any>("/api/webhooks", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: any) =>
      request<any>(`/api/webhooks/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
      request<void>(`/api/webhooks/${id}`, { method: "DELETE" }),
  },
  schedules: {
    list: () => request<{ items: any[] }>("/api/schedules"),
    get: (id: string) => request<any>(`/api/schedules/${id}`),
    create: (data: any) =>
      request<any>("/api/schedules", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: any) =>
      request<any>(`/api/schedules/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
      request<void>(`/api/schedules/${id}`, { method: "DELETE" }),
  },
  runs: {
    list: (params?: { status?: string; agent_id?: string; offset?: number; limit?: number }) => {
      const sp = new URLSearchParams();
      if (params?.status) sp.set("status", params.status);
      if (params?.agent_id) sp.set("agent_id", params.agent_id);
      if (params?.offset) sp.set("offset", String(params.offset));
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return request<{ items: any[]; total: number }>(`/api/runs${qs ? `?${qs}` : ""}`);
    },
    get: (id: string) => request<any>(`/api/runs/${id}`),
    create: (data: { agent_id: string; instructions?: string }) =>
      request<any>("/api/runs", { method: "POST", body: JSON.stringify(data) }),
    retry: (id: string) =>
      request<any>(`/api/runs/${id}/retry`, { method: "POST" }),
    stop: (id: string) =>
      request<any>(`/api/runs/${id}/stop`, { method: "POST" }),
    pause: (id: string) =>
      request<any>(`/api/runs/${id}/pause`, { method: "POST" }),
    resume: (id: string) =>
      request<any>(`/api/runs/${id}/resume`, { method: "POST" }),
  },
  conversations: {
    list: (offset = 0, limit = 20) =>
      request<{ items: any[]; total: number }>(`/api/conversations?offset=${offset}&limit=${limit}`),
    create: (title?: string, agent_id?: string) =>
      request<any>("/api/conversations", {
        method: "POST",
        body: JSON.stringify({ title, agent_id }),
      }),
    get: (id: string) => request<any>(`/api/conversations/${id}`),
    delete: (id: string) =>
      request<void>(`/api/conversations/${id}`, { method: "DELETE" }),
    messages: (id: string, offset = 0, limit = 50) =>
      request<{ items: any[]; total: number }>(
        `/api/conversations/${id}/messages?offset=${offset}&limit=${limit}`
      ),
  },
};
