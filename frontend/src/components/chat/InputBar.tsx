"use client";

import { useState, useRef, useEffect } from "react";
import { Send } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";

export function InputBar() {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage, sendMessageOrCreate, isStreaming, activeConversationId } = useChatStore();

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    if (activeConversationId) {
      sendMessage(trimmed);
    } else {
      sendMessageOrCreate(trimmed);
    }
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 200) + "px";
    }
  }, [input]);

  return (
    <div className="border-t border-zinc-800 p-4">
      <div className="flex items-end gap-2 max-w-3xl mx-auto">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message Gini..."
          disabled={isStreaming}
          rows={1}
          className="flex-1 bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:opacity-50 placeholder-zinc-500"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || isStreaming}
          className="p-3 bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 disabled:text-zinc-500 rounded-xl transition-colors"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
