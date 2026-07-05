"use client";

import { useState, useEffect } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { api } from "@/lib/api-client";

export interface ToolGrant {
  tool_name: string;
  slot_bindings: Record<string, string>;
}

interface CredentialOption {
  id: string;
  name: string;
  credential_type: string;
}

interface SlotDecl {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

interface CatalogTool {
  name: string;
  description: string;
  requires_approval: boolean;
  default_catalog: boolean;
  open_credential_slots: boolean;
  is_builtin: boolean;
  credential_slots: SlotDecl[];
}

interface AgentGrantsProps {
  toolGrants: ToolGrant[];
  setToolGrants: (grants: ToolGrant[]) => void;
  credentialIds: string[];
  setCredentialIds: (ids: string[]) => void;
}

/**
 * Direct tool + credential grants for an agent, with per-tool credential-slot binding.
 * Works identically for creating and editing — the parent submits the collected state.
 */
export function AgentGrants({
  toolGrants,
  setToolGrants,
  credentialIds,
  setCredentialIds,
}: AgentGrantsProps) {
  const [catalog, setCatalog] = useState<CatalogTool[]>([]);
  const [credentials, setCredentials] = useState<CredentialOption[]>([]);
  const [toolsExpanded, setToolsExpanded] = useState(false);
  const [credsExpanded, setCredsExpanded] = useState(false);

  useEffect(() => {
    api.tools.catalog().then((data) => setCatalog((data as CatalogTool[]) ?? [])).catch(() => {});
    api.credentials.list().then((data) => setCredentials((data as CredentialOption[]) ?? [])).catch(() => {});
  }, []);

  const grantedCreds = credentials.filter((c) => credentialIds.includes(c.id));
  const grantByName = new Map(toolGrants.map((g) => [g.tool_name, g]));

  const toggleCredential = (id: string) => {
    if (credentialIds.includes(id)) {
      setCredentialIds(credentialIds.filter((c) => c !== id));
      // Drop any slot bindings that referenced this credential.
      setToolGrants(
        toolGrants.map((g) => ({
          ...g,
          slot_bindings: Object.fromEntries(
            Object.entries(g.slot_bindings).filter(([, cid]) => cid !== id),
          ),
        })),
      );
    } else {
      setCredentialIds([...credentialIds, id]);
    }
  };

  const toggleTool = (name: string) => {
    if (grantByName.has(name)) {
      setToolGrants(toolGrants.filter((g) => g.tool_name !== name));
    } else {
      setToolGrants([...toolGrants, { tool_name: name, slot_bindings: {} }]);
    }
  };

  const setBinding = (toolName: string, slot: string, credId: string) => {
    setToolGrants(
      toolGrants.map((g) => {
        if (g.tool_name !== toolName) return g;
        const next = { ...g.slot_bindings };
        if (credId) next[slot] = credId;
        else delete next[slot];
        return { ...g, slot_bindings: next };
      }),
    );
  };

  const sortedCatalog = [...catalog].sort((a, b) => a.name.localeCompare(b.name));
  const selectClass =
    "bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500";

  return (
    <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
      {/* Credentials */}
      <div className="space-y-2">
        <button
          type="button"
          onClick={() => setCredsExpanded((v) => !v)}
          className="flex items-center gap-1 text-xs font-medium text-zinc-400"
        >
          {credsExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          Credentials ({credentialIds.length})
        </button>
        {credsExpanded && (
          <div className="flex flex-col gap-1 pl-1">
            {credentials.length === 0 && (
              <p className="text-[11px] text-zinc-600">
                No credentials yet. Create them in Settings, then grant them here.
              </p>
            )}
            {credentials.map((c) => (
              <label key={c.id} className="flex items-center gap-2 text-sm text-zinc-300">
                <input
                  type="checkbox"
                  checked={credentialIds.includes(c.id)}
                  onChange={() => toggleCredential(c.id)}
                  className="w-3.5 h-3.5 rounded border-zinc-600 bg-zinc-800 text-violet-500"
                />
                <span>{c.name}</span>
                <span className="text-[11px] text-zinc-600">({c.credential_type})</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Tools */}
      <div className="space-y-2">
        <button
          type="button"
          onClick={() => setToolsExpanded((v) => !v)}
          className="flex items-center gap-1 text-xs font-medium text-zinc-400"
        >
          {toolsExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          Tools ({toolGrants.length})
        </button>
        {toolsExpanded && (
          <div className="flex flex-col gap-2 pl-1">
            {sortedCatalog.map((tool) => {
              const granted = grantByName.get(tool.name);
              return (
                <div key={tool.name} className="rounded-md border border-zinc-800 p-2">
                  <label className="flex items-center gap-2 text-sm text-zinc-300">
                    <input
                      type="checkbox"
                      checked={!!granted}
                      onChange={() => toggleTool(tool.name)}
                      className="w-3.5 h-3.5 rounded border-zinc-600 bg-zinc-800 text-violet-500"
                    />
                    <span className="font-medium">{tool.name}</span>
                    {tool.requires_approval && (
                      <span className="rounded bg-amber-500/15 px-1 text-[10px] text-amber-400">approval</span>
                    )}
                    {!tool.default_catalog && (
                      <span className="rounded bg-red-500/15 px-1 text-[10px] text-red-400">powerful</span>
                    )}
                  </label>
                  <p className="ml-6 text-[11px] text-zinc-600">{tool.description}</p>

                  {granted && tool.open_credential_slots && (
                    <div className="ml-6 mt-2 space-y-1">
                      <p className="text-[11px] text-zinc-500">
                        Expose granted credentials as GINI_CRED_* env vars:
                      </p>
                      {grantedCreds.length === 0 && (
                        <p className="text-[11px] text-zinc-600">Grant a credential above first.</p>
                      )}
                      {grantedCreds.map((c) => (
                        <label key={c.id} className="flex items-center gap-2 text-xs text-zinc-300">
                          <input
                            type="checkbox"
                            checked={Object.values(granted.slot_bindings).includes(c.id)}
                            onChange={(e) => setBinding(tool.name, c.name, e.target.checked ? c.id : "")}
                            className="w-3.5 h-3.5 rounded border-zinc-600 bg-zinc-800 text-violet-500"
                          />
                          {c.name}
                        </label>
                      ))}
                    </div>
                  )}

                  {granted && !tool.open_credential_slots && tool.credential_slots.length > 0 && (
                    <div className="ml-6 mt-2 space-y-2">
                      {tool.credential_slots.map((slot) => (
                        <div key={slot.name} className="text-xs text-zinc-400">
                          <div className="flex items-center gap-2">
                            <span className="min-w-24">
                              {slot.name}
                              {slot.required && <span className="text-red-400">*</span>}
                            </span>
                            <select
                              value={granted.slot_bindings[slot.name] ?? ""}
                              onChange={(e) => setBinding(tool.name, slot.name, e.target.value)}
                              className={selectClass}
                            >
                              <option value="">{slot.required ? "— select credential —" : "— none / auto —"}</option>
                              {grantedCreds.map((c) => (
                                <option key={c.id} value={c.id}>
                                  {c.name}
                                </option>
                              ))}
                            </select>
                          </div>
                          {slot.description && <p className="ml-2 mt-0.5 text-zinc-600">{slot.description}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
