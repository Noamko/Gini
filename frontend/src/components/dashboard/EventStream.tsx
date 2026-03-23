"use client";

import { Activity } from "lucide-react";
import type { DashboardEvent } from "@/stores/dashboardStore";

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const STATUS_COLORS: Record<string, string> = {
  completed: "text-emerald-400",
  pending: "text-amber-400",
  failed: "text-red-400",
  error: "text-red-400",
};

function EventRow({ event }: { event: DashboardEvent }) {
  const statusColor = STATUS_COLORS[event.status] || "text-zinc-400";

  return (
    <div className="flex items-start gap-3 py-2 border-b border-zinc-800/50 last:border-0">
      <span className="text-[11px] text-zinc-600 font-mono mt-0.5 shrink-0">
        {formatTime(event.created_at)}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-zinc-300">{event.event_type}</span>
          <span className={`text-[10px] ${statusColor}`}>{event.status}</span>
        </div>
        <p className="text-xs text-zinc-500 truncate">{event.source}</p>
      </div>
    </div>
  );
}

export function EventStream({ events }: { events: DashboardEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="text-center py-8 text-zinc-500 text-sm">
        No events yet
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Activity size={14} className="text-zinc-400" />
        <h3 className="text-sm font-medium text-zinc-300">Recent Events</h3>
      </div>
      <div className="max-h-80 overflow-y-auto space-y-0">
        {events.map((event) => (
          <EventRow key={event.id} event={event} />
        ))}
      </div>
    </div>
  );
}
