"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Plus, MessageSquare, Trash2, Bot, Settings, Zap, LayoutDashboard, Brain, Activity, Sun, Moon, Play } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useTheme } from "@/components/layout/ThemeProvider";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/runs", label: "Runs", icon: Play },
  { href: "/skills", label: "Skills", icon: Zap },
  { href: "/traces", label: "Traces", icon: Activity },
  { href: "/memories", label: "Memories", icon: Brain },
  { href: "/settings", label: "Settings", icon: Settings },
];

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      onClick={toggleTheme}
      className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
      title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
    >
      {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
    </button>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const {
    conversations,
    activeConversationId,
    loadingConversations,
    loadConversations,
    createConversation,
    selectConversation,
    deleteConversation,
  } = useChatStore();

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  const handleNew = async () => {
    const id = await createConversation();
    selectConversation(id);
  };

  const isChat = pathname?.startsWith("/chat");

  return (
    <aside className="w-64 bg-zinc-900 border-r border-zinc-800 flex flex-col h-full">
      {/* Navigation */}
      <div className="p-2 border-b border-zinc-800 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
              pathname?.startsWith(href)
                ? "bg-zinc-800 text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
            )}
          >
            <Icon size={16} />
            {label}
          </Link>
        ))}
      </div>

      {/* New Chat button (only on chat pages) */}
      {isChat && (
        <div className="p-3 border-b border-zinc-800">
          <button
            onClick={handleNew}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm transition-colors"
          >
            <Plus size={16} />
            New Chat
          </button>
        </div>
      )}

      {/* Conversation list (only on chat pages) */}
      {isChat && (
        <nav className="flex-1 overflow-y-auto p-2 space-y-1">
          {loadingConversations && (
            <p className="text-xs text-zinc-500 px-3 py-2">Loading...</p>
          )}
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={cn(
                "group flex items-center gap-2 px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors",
                activeConversationId === conv.id
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
              )}
              onClick={() => selectConversation(conv.id)}
            >
              <MessageSquare size={14} className="shrink-0" />
              <span className="truncate flex-1">{conv.title || "Untitled"}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteConversation(conv.id);
                }}
                className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 transition-opacity"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </nav>
      )}

      {/* Spacer when not on chat page */}
      {!isChat && <div className="flex-1" />}

      <div className="p-3 border-t border-zinc-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Gini v0.1.0
          </div>
          <ThemeToggle />
        </div>
      </div>
    </aside>
  );
}
