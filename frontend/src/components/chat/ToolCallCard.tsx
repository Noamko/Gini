"use client";

import { cn } from "@/lib/utils";
import { Wrench, CheckCircle, XCircle, Loader2, ArrowRightLeft } from "lucide-react";
import { useState } from "react";

interface Props {
  toolName: string;
  arguments: Record<string, unknown>;
  result?: {
    success: boolean;
    output: string;
    error?: string | null;
    durationMs?: number;
  };
  isExecuting?: boolean;
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

export function ToolCallCard({ toolName, arguments: args, result, isExecuting, delegation }: Props) {
  const [expanded, setExpanded] = useState(false);

  const isDelegation = !!delegation;
  const icon = isDelegation ? (
    delegation.isRunning ? (
      <Loader2 size={14} className="text-purple-400 animate-spin" />
    ) : delegation.success ? (
      <CheckCircle size={14} className="text-emerald-400" />
    ) : (
      <XCircle size={14} className="text-red-400" />
    )
  ) : isExecuting ? (
    <Loader2 size={14} className="text-blue-400 animate-spin" />
  ) : result?.success ? (
    <CheckCircle size={14} className="text-emerald-400" />
  ) : result ? (
    <XCircle size={14} className="text-red-400" />
  ) : (
    <Wrench size={14} className="text-zinc-400" />
  );

  const label = isDelegation
    ? `delegate -> ${delegation.agentName}`
    : toolName;

  const statusText = isDelegation
    ? delegation.isRunning
      ? "running..."
      : delegation.durationMs
        ? `${delegation.durationMs}ms`
        : ""
    : isExecuting
      ? "executing..."
      : result?.durationMs
        ? `${result.durationMs}ms`
        : "";

  return (
    <div className={cn(
      "my-2 rounded-xl border overflow-hidden text-sm",
      isDelegation ? "border-purple-800/50 bg-purple-950/20" : "border-zinc-800 bg-zinc-900/50",
    )}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-zinc-800/50 transition-colors"
      >
        {icon}
        <span className={cn("font-mono text-xs", isDelegation ? "text-purple-400" : "text-violet-400")}>
          {label}
        </span>
        {isDelegation && delegation.costUsd != null && !delegation.isRunning && (
          <span className="text-[10px] text-zinc-500">${delegation.costUsd.toFixed(4)}</span>
        )}
        <span className="text-[11px] text-zinc-500 ml-auto">
          {statusText}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-zinc-800 px-3 py-2 space-y-2">
          {isDelegation && delegation.task && (
            <div>
              <p className="text-[11px] text-zinc-500 mb-1">Task</p>
              <p className="text-xs text-zinc-300">{delegation.task}</p>
            </div>
          )}
          {!isDelegation && (
            <div>
              <p className="text-[11px] text-zinc-500 mb-1">Arguments</p>
              <pre className="text-xs text-zinc-300 bg-zinc-950 rounded-lg p-2 overflow-x-auto">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          )}
          {isDelegation && delegation.content && !delegation.isRunning && (
            <div>
              <p className="text-[11px] text-zinc-500 mb-1">
                {delegation.success ? "Result" : "Error"}
              </p>
              <pre
                className={cn(
                  "text-xs rounded-lg p-2 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap",
                  delegation.success ? "text-zinc-300 bg-zinc-950" : "text-red-300 bg-red-950/30"
                )}
              >
                {delegation.content}
              </pre>
            </div>
          )}
          {!isDelegation && result && (
            <div>
              <p className="text-[11px] text-zinc-500 mb-1">
                {result.success ? "Output" : "Error"}
              </p>
              <pre
                className={cn(
                  "text-xs rounded-lg p-2 overflow-x-auto max-h-48 overflow-y-auto",
                  result.success ? "text-zinc-300 bg-zinc-950" : "text-red-300 bg-red-950/30"
                )}
              >
                {result.success ? result.output : result.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
