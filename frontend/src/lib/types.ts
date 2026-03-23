export interface Agent {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  llm_provider: string;
  llm_model: string;
  temperature: number;
  max_tokens: number;
  state: string;
  is_main: boolean;
  is_active: boolean;
  auto_approve: boolean;
  daily_budget_usd: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  title: string | null;
  agent_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string | null;
  tool_calls: Record<string, unknown> | null;
  tool_call_id: string | null;
  token_count: number | null;
  model_used: string | null;
  cost_usd: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

// WebSocket message types
export interface WSUserMessage {
  type: "user_message";
  content: string;
}

export interface WSAssistantChunk {
  type: "assistant_chunk";
  content: string;
}

export interface WSAssistantComplete {
  type: "assistant_message_complete";
  content: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_ms: number;
}

export interface WSError {
  type: "error";
  message: string;
}

export type WSServerMessage = WSAssistantChunk | WSAssistantComplete | WSError;
