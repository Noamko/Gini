"use client";

import { useEffect, useState, useCallback } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { DollarSign } from "lucide-react";

interface PricingModel {
  id: string;
  provider: string;
  input_per_1m: number;
  output_per_1m: number;
}

const API_URL = typeof window !== "undefined"
  ? (window.location.port ? `http://${window.location.hostname}:8000` : window.location.origin)
  : "http://localhost:8000";

export default function PricingPage() {
  const [pricing, setPricing] = useState<PricingModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/api/pricing`)
      .then((r) => r.json())
      .then((d) => setPricing(d.models))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const providers = ["anthropic", "openai"];

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-3 pt-14 md:p-6 md:pt-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <div>
            <h1 className="text-2xl font-bold">Pricing</h1>
            <p className="text-sm text-zinc-500 mt-1">
              Cost per 1M tokens (USD). Tracked locally for Gini usage only.
            </p>
          </div>

          {loading ? (
            <p className="text-sm text-zinc-500">Loading pricing...</p>
          ) : (
            providers.map((provider) => {
              const models = pricing.filter((m) => m.provider === provider);
              if (models.length === 0) return null;
              return (
                <section key={provider} className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
                  <div className="px-4 py-3 bg-zinc-800/50 flex items-center gap-2">
                    <DollarSign size={14} className="text-emerald-400" />
                    <span className="text-sm font-medium text-zinc-200 capitalize">{provider}</span>
                    <span className="text-xs text-zinc-500">{models.length} models</span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-zinc-500 border-b border-zinc-800">
                          <th className="text-left px-4 py-2.5 font-medium">Model</th>
                          <th className="text-right px-4 py-2.5 font-medium">Input / 1M</th>
                          <th className="text-right px-4 py-2.5 font-medium">Output / 1M</th>
                          <th className="text-right px-4 py-2.5 font-medium hidden md:table-cell">~1K Input</th>
                          <th className="text-right px-4 py-2.5 font-medium hidden md:table-cell">~1K Output</th>
                        </tr>
                      </thead>
                      <tbody>
                        {models.map((m) => (
                          <tr key={m.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                            <td className="px-4 py-2 font-mono text-zinc-300 text-xs">{m.id}</td>
                            <td className="px-4 py-2 text-right text-zinc-400">${m.input_per_1m.toFixed(2)}</td>
                            <td className="px-4 py-2 text-right text-zinc-400">${m.output_per_1m.toFixed(2)}</td>
                            <td className="px-4 py-2 text-right text-zinc-500 hidden md:table-cell">${(m.input_per_1m / 1000).toFixed(4)}</td>
                            <td className="px-4 py-2 text-right text-zinc-500 hidden md:table-cell">${(m.output_per_1m / 1000).toFixed(4)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              );
            })
          )}
        </div>
      </main>
    </div>
  );
}
