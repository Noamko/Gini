"use client";

import { useEffect, useRef } from "react";
import { useChatStore } from "@/stores/chatStore";
import { MessageBubble } from "./MessageBubble";
import { InputBar } from "./InputBar";
import { Bot } from "lucide-react";

export function ChatPanel() {
  const { messages, activeConversationId, isStreaming, wsClient, sendMessage } = useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const pendingSent = useRef(false);

  // Auto-scroll on new messages
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  // Send pending agent message from sessionStorage (set by Run Agent)
  useEffect(() => {
    if (!activeConversationId || isStreaming || pendingSent.current) return;
    const raw = sessionStorage.getItem("pending_agent_message");
    if (!raw) return;

    let parsed: { conversationId: string; content: string };
    try {
      parsed = JSON.parse(raw);
    } catch {
      sessionStorage.removeItem("pending_agent_message");
      return;
    }
    if (parsed.conversationId !== activeConversationId || !parsed.content) return;

    // Poll until WS is connected, then send
    const timer = setInterval(() => {
      const ws = useChatStore.getState().wsClient;
      if (ws?.isConnected) {
        clearInterval(timer);
        sessionStorage.removeItem("pending_agent_message");
        pendingSent.current = true;
        sendMessage(parsed.content);
      }
    }, 100);
    return () => clearInterval(timer);
  }, [activeConversationId, isStreaming, sendMessage]);

  if (!activeConversationId) {
    return (
      <div className="flex-1 flex flex-col">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-violet-600/20 flex items-center justify-center mx-auto">
              <Bot size={32} className="text-violet-400" />
            </div>
            <h2 className="text-xl font-semibold text-zinc-300">Welcome to Gini</h2>
            <p className="text-sm text-zinc-500">
              Create a new conversation or select an existing one to start chatting.
            </p>
          </div>
        </div>
        <InputBar />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-2 md:px-4 pt-12 md:pt-0">
        <div className="max-w-3xl mx-auto py-4">
          {messages.length === 0 && (
            <div className="flex items-center justify-center h-32 text-sm text-zinc-500">
              Send a message to start the conversation.
            </div>
          )}
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              role={msg.role}
              content={msg.content}
              isStreaming={msg.isStreaming}
              model={msg.model}
              tokens={msg.tokens}
              cost={msg.cost}
              durationMs={msg.durationMs}
              toolCalls={msg.toolCalls}
              approvals={msg.approvals}
              thinking={msg.thinking}
            />
          ))}
        </div>
      </div>
      <InputBar />
    </div>
  );
}
