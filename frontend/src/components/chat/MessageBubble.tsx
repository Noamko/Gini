"use client";

import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import { Bot, User, Brain } from "lucide-react";
import { ToolCallCard } from "./ToolCallCard";
import { HITLApprovalCard } from "./HITLApprovalCard";
import type { ToolCall, ApprovalRequest } from "@/stores/chatStore";

interface Props {
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

export function MessageBubble({ role, content, isStreaming, model, tokens, cost, durationMs, toolCalls, approvals, thinking }: Props) {
  const isUser = role === "user";

  return (
    <div className={cn("flex gap-2 md:gap-3 py-3 md:py-4", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="shrink-0 w-7 h-7 md:w-8 md:h-8 rounded-full bg-violet-600 flex items-center justify-center">
          <Bot size={14} />
        </div>
      )}

      <div className={cn("max-w-[90%] md:max-w-[75%] space-y-1", isUser && "order-first")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "bg-blue-600 text-white"
              : "bg-zinc-800 text-zinc-100"
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{content}</p>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown>{content || ""}</ReactMarkdown>
              {isStreaming && (
                <span className="inline-block w-2 h-4 bg-zinc-400 animate-pulse ml-0.5" />
              )}
            </div>
          )}
        </div>

        {!isUser && thinking && thinking.length > 0 && (
          <div className="space-y-1.5">
            {thinking.map((t, i) => (
              <div key={i} className="rounded-xl border border-zinc-700/50 bg-zinc-800/30 px-3 py-2">
                <div className="flex items-center gap-1.5 mb-1">
                  <Brain size={12} className="text-zinc-500" />
                  <span className="text-[10px] text-zinc-500 uppercase tracking-wider">Thinking</span>
                </div>
                <p className="text-xs text-zinc-400 italic">{t}</p>
              </div>
            ))}
          </div>
        )}

        {!isUser && approvals && approvals.length > 0 && (
          <div>
            {approvals.map((a) => (
              <HITLApprovalCard
                key={a.approvalId}
                approvalId={a.approvalId}
                toolName={a.toolName}
                arguments={a.arguments}
                status={a.status}
              />
            ))}
          </div>
        )}

        {!isUser && toolCalls && toolCalls.length > 0 && (
          <div>
            {toolCalls.map((tc) => (
              <ToolCallCard
                key={tc.id}
                toolName={tc.toolName}
                arguments={tc.arguments}
                result={tc.result}
                isExecuting={tc.isExecuting}
                delegation={tc.delegation}
              />
            ))}
          </div>
        )}

        {!isUser && !isStreaming && model && (
          <div className="flex items-center gap-2 text-[11px] text-zinc-500 px-1">
            <span>{model}</span>
            {tokens != null && <span>{tokens} tokens</span>}
            {cost != null && <span>${cost.toFixed(4)}</span>}
            {durationMs != null && <span>{(durationMs / 1000).toFixed(1)}s</span>}
          </div>
        )}
      </div>

      {isUser && (
        <div className="shrink-0 w-8 h-8 rounded-full bg-zinc-700 flex items-center justify-center">
          <User size={16} />
        </div>
      )}
    </div>
  );
}
