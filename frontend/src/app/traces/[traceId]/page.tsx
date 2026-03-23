"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Clock, Coins, Zap, Bot, Wrench, ArrowRightLeft, AlertCircle } from "lucide-react";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

interface Step {
  id: string;
  step_type: string;
  step_name: string | null;
  step_order: number;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error: string | null;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  model: string | null;
  created_at: string;
}

interface TraceDetail {
  trace_id: string;
  steps: Step[];
  total_duration_ms: number;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

const STEP_ICONS: Record<string, React.ReactNode> = {
  llm_call: <Bot size={14} />,
  tool_call: <Wrench size={14} />,
  delegation: <ArrowRightLeft size={14} />,
};

const STEP_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  llm_call: { border: "border-blue-800/50", bg: "bg-blue-950/20", text: "text-blue-400" },
  tool_call: { border: "border-amber-800/50", bg: "bg-amber-950/20", text: "text-amber-400" },
  delegation: { border: "border-purple-800/50", bg: "bg-purple-950/20", text: "text-purple-400" },
};

export default function TraceDetailPage() {
  const params = useParams();
  const traceId = params.traceId as string;
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [expandedStep, setExpandedStep] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.traces.get(traceId);
        setTrace(data);
      } catch {
        // ignore
      }
      setLoading(false);
    })();
  }, [traceId]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-500">
        Loading trace...
      </div>
    );
  }

  if (!trace) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-500">
        Trace not found
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto">
      <div className="border-b border-zinc-800 px-6 py-4 flex items-center gap-3">
        <Link href="/traces" className="text-zinc-500 hover:text-zinc-300 transition-colors">
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="text-lg font-semibold text-zinc-100 font-mono">
            {traceId.slice(0, 12)}...
          </h1>
          <div className="flex items-center gap-3 text-xs text-zinc-500 mt-0.5">
            <span className="flex items-center gap-1"><Zap size={10} /> {trace.steps.length} steps</span>
            <span className="flex items-center gap-1"><Clock size={10} /> {(trace.total_duration_ms / 1000).toFixed(2)}s</span>
            <span className="flex items-center gap-1">
              {(trace.total_input_tokens + trace.total_output_tokens).toLocaleString()} tokens
            </span>
            <span className="flex items-center gap-1 text-emerald-400">
              <Coins size={10} /> ${trace.total_cost_usd.toFixed(4)}
            </span>
          </div>
        </div>
      </div>

      <div className="p-6 max-w-4xl mx-auto w-full">
        {/* Timeline */}
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-5 top-0 bottom-0 w-px bg-zinc-800" />

          <div className="space-y-3">
            {trace.steps.map((step, i) => {
              const colors = STEP_COLORS[step.step_type] || STEP_COLORS.llm_call;
              const icon = STEP_ICONS[step.step_type] || <Zap size={14} />;
              const isExpanded = expandedStep === step.id;

              return (
                <div key={step.id} className="relative pl-12">
                  {/* Timeline dot */}
                  <div className={cn(
                    "absolute left-3 top-3 w-5 h-5 rounded-full border-2 flex items-center justify-center",
                    colors.border, colors.bg, colors.text,
                    step.error && "border-red-800/50 bg-red-950/20 text-red-400",
                  )}>
                    {step.error ? <AlertCircle size={10} /> : icon}
                  </div>

                  <button
                    onClick={() => setExpandedStep(isExpanded ? null : step.id)}
                    className={cn(
                      "w-full text-left rounded-xl border p-4 transition-colors",
                      colors.border, colors.bg,
                      "hover:brightness-110",
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={cn("text-xs font-medium uppercase tracking-wider", colors.text)}>
                          {step.step_type}
                        </span>
                        {step.step_name && (
                          <span className="text-xs text-zinc-400 font-mono">{step.step_name}</span>
                        )}
                        {step.model && (
                          <span className="text-[10px] bg-zinc-800 rounded px-1.5 py-0.5 text-zinc-500">
                            {step.model}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-zinc-500">
                        {(step.input_tokens + step.output_tokens) > 0 && (
                          <span>{(step.input_tokens + step.output_tokens).toLocaleString()} tok</span>
                        )}
                        {step.cost_usd > 0 && (
                          <span className="text-emerald-400">${step.cost_usd.toFixed(4)}</span>
                        )}
                        <span>{step.duration_ms.toFixed(0)}ms</span>
                      </div>
                    </div>

                    {step.error && (
                      <p className="mt-2 text-xs text-red-400">{step.error}</p>
                    )}
                  </button>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className={cn("mt-1 rounded-xl border p-4 space-y-3", colors.border, "bg-zinc-950/50")}>
                      {step.input_data && (
                        <div>
                          <p className="text-[11px] text-zinc-500 mb-1 uppercase tracking-wider">Input</p>
                          <pre className="text-xs text-zinc-300 bg-zinc-900 rounded-lg p-3 overflow-x-auto max-h-64 overflow-y-auto">
                            {JSON.stringify(step.input_data, null, 2)}
                          </pre>
                        </div>
                      )}
                      {step.output_data && (
                        <div>
                          <p className="text-[11px] text-zinc-500 mb-1 uppercase tracking-wider">Output</p>
                          <pre className="text-xs text-zinc-300 bg-zinc-900 rounded-lg p-3 overflow-x-auto max-h-64 overflow-y-auto">
                            {JSON.stringify(step.output_data, null, 2)}
                          </pre>
                        </div>
                      )}
                      <div className="flex gap-4 text-[11px] text-zinc-500">
                        <span>Step #{step.step_order}</span>
                        <span>Input: {step.input_tokens} tok</span>
                        <span>Output: {step.output_tokens} tok</span>
                        <span>{new Date(step.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
