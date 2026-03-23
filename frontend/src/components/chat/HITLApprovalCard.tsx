"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { ShieldAlert, Check, X, Loader2 } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";

interface Props {
  approvalId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  status: "pending" | "approved" | "rejected";
}

export function HITLApprovalCard({ approvalId, toolName, arguments: args, status }: Props) {
  const { wsClient } = useChatStore();
  const [localStatus, setLocalStatus] = useState<"idle" | "approving" | "rejecting">("idle");

  const effectiveStatus = localStatus === "approving" ? "approved" : localStatus === "rejecting" ? "rejected" : status;

  const handleApprove = () => {
    setLocalStatus("approving");
    wsClient?.send({
      type: "approval_response",
      approval_id: approvalId,
      approved: true,
    });
  };

  const handleReject = () => {
    setLocalStatus("rejecting");
    wsClient?.send({
      type: "approval_response",
      approval_id: approvalId,
      approved: false,
      reason: "User rejected",
    });
  };

  return (
    <div className="my-2 rounded-xl border border-amber-800/50 bg-amber-950/20 overflow-hidden text-sm">
      <div className="flex items-center gap-2 px-3 py-2">
        <ShieldAlert size={14} className="text-amber-400" />
        <span className="text-amber-300 font-medium text-xs">Approval Required</span>
      </div>

      <div className="border-t border-amber-800/30 px-3 py-2 space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-zinc-500">Tool:</span>
          <span className="font-mono text-xs text-violet-400">{toolName}</span>
        </div>

        <div>
          <p className="text-[11px] text-zinc-500 mb-1">Arguments</p>
          <pre className="text-xs text-zinc-300 bg-zinc-950 rounded-lg p-2 overflow-x-auto max-h-32 overflow-y-auto">
            {JSON.stringify(args, null, 2)}
          </pre>
        </div>

        {effectiveStatus === "pending" && (
          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={handleApprove}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors"
            >
              <Check size={12} />
              Approve
            </button>
            <button
              onClick={handleReject}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-medium transition-colors"
            >
              <X size={12} />
              Reject
            </button>
          </div>
        )}

        {effectiveStatus === "approved" && (
          <div className="flex items-center gap-1.5 text-xs text-emerald-400 pt-1">
            {localStatus === "approving" && <Loader2 size={12} className="animate-spin" />}
            {localStatus !== "approving" && <Check size={12} />}
            <span>{localStatus === "approving" ? "Approving..." : "Approved"}</span>
          </div>
        )}

        {effectiveStatus === "rejected" && (
          <div className="flex items-center gap-1.5 text-xs text-red-400 pt-1">
            <X size={12} />
            <span>Rejected</span>
          </div>
        )}
      </div>
    </div>
  );
}
