"use client";

import { cn } from "@/lib/utils";
import { Wrench, CheckCircle, XCircle, Loader2, ArrowRightLeft, Terminal, FileText, Globe, Send, ChevronDown, ChevronUp } from "lucide-react";
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

const TOOL_ICONS: Record<string, React.ReactNode> = {
  run_shell: <Terminal size={13} />,
  read_file: <FileText size={13} />,
  write_file: <FileText size={13} />,
  web_fetch: <Globe size={13} />,
  send_telegram: <Send size={13} />,
  delegate_task: <ArrowRightLeft size={13} />,
};

function toolSummary(name: string, args: Record<string, unknown>): string {
  switch (name) {
    case "run_shell":
      return `$ ${(args.command as string || "").slice(0, 120)}`;
    case "read_file":
      return `Read ${args.path || "file"}`;
    case "write_file":
      return `Write ${args.path || "file"} (${((args.content as string) || "").length} chars)`;
    case "web_fetch": {
      const method = (args.method as string) || "GET";
      return `${method} ${(args.url as string || "").slice(0, 100)}`;
    }
    case "send_telegram":
      return `Send to ${args.chat_id}: "${(args.text as string || "").slice(0, 60)}"`;
    default:
      return Object.entries(args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ").slice(0, 120);
  }
}

export function ToolCallCard({ toolName, arguments: args, result, isExecuting, delegation }: Props) {
  const [expanded, setExpanded] = useState(false);

  const isDelegation = !!delegation;
  const statusIcon = isDelegation ? (
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

  const toolIcon = isDelegation
    ? <ArrowRightLeft size={13} className="text-purple-400" />
    : (TOOL_ICONS[toolName] || <Wrench size={13} />);

  const summary = isDelegation
    ? delegation.task?.slice(0, 120) || delegation.agentName
    : toolSummary(toolName, args);

  const label = isDelegation
    ? `delegate → ${delegation.agentName}`
    : toolName;

  const durationText = isDelegation
    ? (delegation.durationMs ? `${(delegation.durationMs / 1000).toFixed(1)}s` : "")
    : (result?.durationMs ? `${(result.durationMs / 1000).toFixed(1)}s` : "");

  // Show inline preview for shell output (first few lines)
  const hasOutput = !isDelegation && result?.success && result.output;
  const outputPreview = hasOutput ? result.output.split("\n").slice(0, 3).join("\n") : "";
  const outputTruncated = hasOutput && result.output.split("\n").length > 3;

  return (
    <div className={cn(
      "my-2 rounded-xl border overflow-hidden text-sm",
      isDelegation ? "border-purple-800/50 bg-purple-950/20" : "border-zinc-800 bg-zinc-900/50",
    )}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-3 py-2 hover:bg-zinc-800/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          {statusIcon}
          <span className="text-zinc-500">{toolIcon}</span>
          <span className={cn("font-mono text-xs font-medium", isDelegation ? "text-purple-400" : "text-violet-400")}>
            {label}
          </span>
          {isDelegation && delegation.costUsd != null && !delegation.isRunning && (
            <span className="text-[10px] text-zinc-500">${delegation.costUsd.toFixed(4)}</span>
          )}
          <span className="text-[11px] text-zinc-600 ml-auto flex items-center gap-1">
            {durationText}
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </span>
        </div>
        {/* Summary line — always visible */}
        <p className="text-[11px] text-zinc-500 mt-1 font-mono truncate pl-6">
          {summary}
        </p>
        {/* Inline output preview for shell commands */}
        {!expanded && outputPreview && (
          <pre className="text-[11px] text-zinc-400 mt-1 pl-6 font-mono truncate max-h-12 overflow-hidden">
            {outputPreview}{outputTruncated ? "\n..." : ""}
          </pre>
        )}
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-zinc-800 px-3 py-2 space-y-2">
          {/* Delegation task */}
          {isDelegation && delegation.task && (
            <div>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Task</p>
              <p className="text-xs text-zinc-300">{delegation.task}</p>
            </div>
          )}

          {/* Tool arguments */}
          {!isDelegation && (
            <div>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">
                {toolName === "run_shell" ? "Command" : toolName === "web_fetch" ? "Request" : "Arguments"}
              </p>
              {toolName === "run_shell" ? (
                <pre className="text-xs text-emerald-300 bg-zinc-950 rounded-lg p-2 overflow-x-auto font-mono">
                  $ {args.command as string}
                </pre>
              ) : toolName === "write_file" ? (
                <div className="space-y-1">
                  <p className="text-xs text-zinc-300 font-mono">{args.path as string}</p>
                  <pre className="text-xs text-zinc-400 bg-zinc-950 rounded-lg p-2 overflow-x-auto max-h-48 overflow-y-auto">
                    {(args.content as string || "").slice(0, 2000)}
                  </pre>
                </div>
              ) : (
                <pre className="text-xs text-zinc-300 bg-zinc-950 rounded-lg p-2 overflow-x-auto max-h-32 overflow-y-auto">
                  {JSON.stringify(args, null, 2)}
                </pre>
              )}
            </div>
          )}

          {/* Delegation result */}
          {isDelegation && delegation.content && !delegation.isRunning && (
            <div>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">
                {delegation.success ? "Result" : "Error"}
              </p>
              <pre className={cn(
                "text-xs rounded-lg p-2 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap",
                delegation.success ? "text-zinc-300 bg-zinc-950" : "text-red-300 bg-red-950/30"
              )}>
                {delegation.content}
              </pre>
            </div>
          )}

          {/* Tool output */}
          {!isDelegation && result && (
            <div>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">
                {result.success ? "Output" : "Error"}
              </p>
              <pre className={cn(
                "text-xs rounded-lg p-2 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap",
                result.success ? "text-zinc-300 bg-zinc-950" : "text-red-300 bg-red-950/30"
              )}>
                {result.success ? result.output : result.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
