"use client";

import { Sidebar } from "@/components/layout/Sidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";

export default function ChatPage() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <ChatPanel />
    </div>
  );
}
