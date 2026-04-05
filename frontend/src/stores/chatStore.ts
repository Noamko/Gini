"use client";

import { create } from "zustand";
import type { Conversation, Message } from "@/lib/types";
import { api } from "@/lib/api-client";
import { WSClient } from "@/lib/ws-client";

export interface ToolCall {
  id: string;
  toolName: string;
  arguments: Record<string, unknown>;
  isExecuting: boolean;
  result?: {
    success: boolean;
    output: string;
    error?: string | null;
    durationMs?: number;
  };
  delegation?: {
    agentName: string;
    task: string;
    isRunning: boolean;
    success?: boolean;
    content?: string;
    costUsd?: number;
    durationMs?: number;
  };
}

export interface ApprovalRequest {
  approvalId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  toolCallId: string;
  status: "pending" | "approved" | "rejected";
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  model?: string;
  tokens?: number;
  cost?: number;
  durationMs?: number;
  toolCalls?: ToolCall[];
  approvals?: ApprovalRequest[];
  thinking?: string[];
}

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  loadingConversations: boolean;
  messages: ChatMessage[];
  isStreaming: boolean;
  wsClient: WSClient | null;

  loadConversations: () => Promise<void>;
  createConversation: (title?: string) => Promise<string>;
  selectConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  sendMessage: (content: string) => void;
  sendMessageOrCreate: (content: string) => Promise<void>;
  connectWS: (conversationId: string) => void;
  disconnectWS: () => void;
}

let messageIdCounter = 0;
const tempId = () => `temp-${++messageIdCounter}`;

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  loadingConversations: false,
  messages: [],
  isStreaming: false,
  wsClient: null,

  loadConversations: async () => {
    set({ loadingConversations: true });
    try {
      const data = await api.conversations.list(0, 100);
      set({ conversations: data.items, loadingConversations: false });
    } catch {
      set({ loadingConversations: false });
    }
  },

  createConversation: async (title?: string) => {
    const conv = await api.conversations.create(title || "New Chat");
    set((s) => ({ conversations: [conv, ...s.conversations] }));
    return conv.id;
  },

  selectConversation: async (id: string) => {
    const { wsClient } = get();
    wsClient?.disconnect();

    set({ activeConversationId: id, messages: [], isStreaming: false });

    try {
      const data = await api.conversations.messages(id);
      const msgs: ChatMessage[] = data.items
        .filter(
          (m: Message) =>
            (m.role === "user" || m.role === "assistant") &&
            !m.metadata?.hidden_from_ui
        )
        .map((m: Message) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content || "",
          model: m.model_used || undefined,
          tokens: m.token_count || undefined,
          cost: m.cost_usd ? Number(m.cost_usd) : undefined,
        }));
      set({ messages: msgs });
    } catch {
      // conversation might be new
    }

    get().connectWS(id);
  },

  deleteConversation: async (id: string) => {
    await api.conversations.delete(id);
    const { activeConversationId } = get();
    set((s) => ({
      conversations: s.conversations.filter((c) => c.id !== id),
      ...(activeConversationId === id
        ? { activeConversationId: null, messages: [] }
        : {}),
    }));
    if (activeConversationId === id) {
      get().disconnectWS();
    }
  },

  sendMessage: (content: string) => {
    const { wsClient, isStreaming } = get();
    if (!wsClient || isStreaming) return;

    const userMsg: ChatMessage = { id: tempId(), role: "user", content };
    const assistantMsg: ChatMessage = {
      id: tempId(),
      role: "assistant",
      content: "",
      isStreaming: true,
      toolCalls: [],
      approvals: [],
    };

    set((s) => ({
      messages: [...s.messages, userMsg, assistantMsg],
      isStreaming: true,
    }));

    wsClient.send({ type: "user_message", content });
  },

  sendMessageOrCreate: async (content: string) => {
    const { activeConversationId, isStreaming } = get();
    if (isStreaming) return;

    if (activeConversationId) {
      get().sendMessage(content);
      return;
    }

    // Auto-create conversation, select it (which connects WS), then send
    const conv = await api.conversations.create(content.slice(0, 50) || "New Chat");
    set((s) => ({ conversations: [conv, ...s.conversations] }));
    // Select the conversation (loads messages + connects WS)
    set({ activeConversationId: conv.id, messages: [], isStreaming: false });
    get().connectWS(conv.id);

    // Wait for WS to connect, then send
    await new Promise<void>((resolve) => {
      const check = () => {
        const ws = get().wsClient;
        if (ws?.isConnected) {
          resolve();
        } else {
          setTimeout(check, 50);
        }
      };
      check();
    });
    get().sendMessage(content);
  },

  connectWS: (conversationId: string) => {
    const client = new WSClient(`/ws/chat/${conversationId}`);

    client.onMessage((data) => {
      if (data.type === "assistant_thinking") {
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming) {
            const thinking = [...(last.thinking || []), data.content];
            msgs[msgs.length - 1] = { ...last, thinking };
          }
          return { messages: msgs };
        });

      } else if (data.type === "assistant_chunk") {
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming) {
            msgs[msgs.length - 1] = { ...last, content: last.content + data.content };
          }
          return { messages: msgs };
        });

      } else if (data.type === "approval_request") {
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming) {
            const approvals = [...(last.approvals || [])];
            approvals.push({
              approvalId: data.approval_id,
              toolName: data.tool_name,
              arguments: data.arguments,
              toolCallId: data.tool_call_id,
              status: "pending",
            });
            msgs[msgs.length - 1] = { ...last, approvals };
          }
          return { messages: msgs };
        });

      } else if (data.type === "tool_call_start") {
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming) {
            // If this tool had an approval, mark it as approved
            const approvals = (last.approvals || []).map((a) =>
              a.toolCallId === data.tool_call_id ? { ...a, status: "approved" as const } : a
            );
            const toolCalls = [...(last.toolCalls || [])];
            toolCalls.push({
              id: data.tool_call_id,
              toolName: data.tool_name,
              arguments: data.arguments,
              isExecuting: true,
            });
            msgs[msgs.length - 1] = { ...last, toolCalls, approvals };
          }
          return { messages: msgs };
        });

      } else if (data.type === "tool_call_result") {
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming) {
            // Check if this is a rejection (no tool_call_start was sent)
            const hasToolCall = last.toolCalls?.some((tc) => tc.id === data.tool_call_id);
            if (!hasToolCall && !data.success) {
              // This was a rejected approval — mark the approval as rejected
              const approvals = (last.approvals || []).map((a) =>
                a.toolCallId === data.tool_call_id ? { ...a, status: "rejected" as const } : a
              );
              msgs[msgs.length - 1] = { ...last, approvals };
            } else if (last.toolCalls) {
              const toolCalls = last.toolCalls.map((tc) =>
                tc.id === data.tool_call_id
                  ? {
                      ...tc,
                      isExecuting: false,
                      result: {
                        success: data.success,
                        output: data.output,
                        error: data.error,
                        durationMs: data.duration_ms,
                      },
                    }
                  : tc
              );
              msgs[msgs.length - 1] = { ...last, toolCalls };
            }
          }
          return { messages: msgs };
        });

      } else if (data.type === "delegation_start") {
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming) {
            const toolCalls = [...(last.toolCalls || [])];
            toolCalls.push({
              id: data.tool_call_id,
              toolName: "delegate_task",
              arguments: { agent_name: data.agent_name, task: data.task },
              isExecuting: true,
              delegation: {
                agentName: data.agent_name,
                task: data.task,
                isRunning: true,
              },
            });
            msgs[msgs.length - 1] = { ...last, toolCalls };
          }
          return { messages: msgs };
        });

      } else if (data.type === "delegation_complete") {
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming && last.toolCalls) {
            const toolCalls = last.toolCalls.map((tc) =>
              tc.id === data.tool_call_id
                ? {
                    ...tc,
                    isExecuting: false,
                    delegation: {
                      ...tc.delegation!,
                      isRunning: false,
                      success: data.success,
                      content: data.content,
                      costUsd: data.cost_usd,
                      durationMs: data.duration_ms,
                    },
                    result: {
                      success: data.success,
                      output: data.content || "",
                      durationMs: data.duration_ms,
                    },
                  }
                : tc
            );
            msgs[msgs.length - 1] = { ...last, toolCalls };
          }
          return { messages: msgs };
        });

      } else if (data.type === "assistant_message_complete") {
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming) {
            msgs[msgs.length - 1] = {
              ...last,
              content: data.content,
              isStreaming: false,
              model: data.model,
              tokens: data.input_tokens + data.output_tokens,
              cost: data.cost_usd,
              durationMs: data.duration_ms,
            };
          }
          return { messages: msgs, isStreaming: false };
        });

      } else if (data.type === "error") {
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming) {
            msgs[msgs.length - 1] = {
              ...last,
              content: `Error: ${data.message}`,
              isStreaming: false,
            };
          }
          return { messages: msgs, isStreaming: false };
        });

      } else if (data.type === "_ws_reconnected") {
        // WS reconnected — any in-flight streaming/approvals are stale
        set((s) => {
          if (!s.isStreaming) return s;
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.isStreaming) {
            msgs[msgs.length - 1] = {
              ...last,
              content: last.content || "(Connection lost — please resend your message)",
              isStreaming: false,
            };
          }
          return { messages: msgs, isStreaming: false };
        });
      }
    });

    client.connect();
    set({ wsClient: client });
  },

  disconnectWS: () => {
    get().wsClient?.disconnect();
    set({ wsClient: null });
  },
}));
