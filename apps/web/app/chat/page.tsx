"use client";

import { useState, useEffect, useCallback } from "react";
import { SessionList } from "@/components/sidebar/SessionList";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { sessions as sessionsAPI } from "@/lib/api";
import type { Session, ChatMessage } from "@/lib/types";
import {
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  LayoutDashboard,
  FileText,
  User,
  Cpu,
} from "lucide-react";
import Link from "next/link";

const NAV_ITEMS = [
  { href: "/chat", label: "Chat", icon: MessageSquarePlus },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/profile", label: "Profil", icon: User },
  { href: "/models", label: "Modeles", icon: Cpu },
];

export default function ChatPage() {
  const [sessionList, setSessionList] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [loading, setLoading] = useState(true);
  // Cache des messages par session : le changement de session est instantane
  // pour une session deja chargee (pas de re-appel reseau).
  const [messagesCache, setMessagesCache] = useState<Record<number, ChatMessage[]>>({});

  // Chargement UNIQUE au montage (avant : re-fetch a chaque changement de
  // session a cause de la dependance activeSessionId).
  useEffect(() => {
    let cancelled = false;
    sessionsAPI.list().then((data) => {
      if (cancelled) return;
      setSessionList(data);
      setActiveSessionId((prev) => prev ?? (data.length > 0 ? data[0].id : null));
    }).catch((err) => {
      console.error("Failed to load sessions:", err);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  const cacheMessages = useCallback((id: number, msgs: ChatMessage[]) => {
    setMessagesCache((prev) => ({ ...prev, [id]: msgs }));
  }, []);

  const handleNewSession = async () => {
    try {
      const session = await sessionsAPI.create("Nouvelle session");
      // Garde-fou : si l'id retourne est invalide, on recharge la liste
      // pour recuperer l'id reel depuis la DB.
      if (!session.id) {
        const data = await sessionsAPI.list();
        setSessionList(data);
        if (data.length > 0) setActiveSessionId(data[0].id);
        return;
      }
      setSessionList((prev) => [session, ...prev]);
      setActiveSessionId(session.id);
    } catch (err) {
      console.error("Failed to create session:", err);
    }
  };

  const handleDeleteSession = async (id: number) => {
    try {
      await sessionsAPI.delete(id);
      setSessionList((prev) => prev.filter((s) => s.id !== id));
      if (activeSessionId === id) {
        const remaining = sessionList.filter((s) => s.id !== id);
        setActiveSessionId(remaining.length > 0 ? remaining[0].id : null);
      }
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  return (
    <div className="flex h-screen">
      {/* ── Sidebar ── */}
      <aside
        className={`flex flex-col border-r border-zinc-800 bg-surface-1 transition-all duration-300 ${
          sidebarOpen ? "w-64" : "w-0 overflow-hidden"
        }`}
      >
        {/* New session button */}
        <div className="flex items-center justify-between p-3 border-b border-zinc-800">
          <span className="text-sm font-medium text-zinc-400">Sessions</span>
          <button
            onClick={handleNewSession}
            className="p-1.5 rounded-md hover:bg-surface-2 text-zinc-400 hover:text-zinc-200 transition-colors"
            title="Nouvelle session"
          >
            <MessageSquarePlus size={16} />
          </button>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto">
          <SessionList
            sessions={sessionList}
            activeId={activeSessionId}
            onSelect={setActiveSessionId}
            onDelete={handleDeleteSession}
            loading={loading}
          />
        </div>

        {/* Bottom nav */}
        <div className="border-t border-zinc-800 p-2 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = item.href === "/chat";
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-surface-2 text-zinc-100"
                    : "text-zinc-400 hover:bg-surface-2 hover:text-zinc-200"
                }`}
              >
                <Icon size={16} />
                {item.label}
              </Link>
            );
          })}
        </div>
      </aside>

      {/* ── Main area ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="flex items-center gap-2 h-12 px-4 border-b border-zinc-800 bg-surface-1/50 backdrop-blur-sm">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 rounded-md hover:bg-surface-2 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
          </button>
          <span className="text-sm font-medium text-zinc-300">
            {sessionList.find((s) => s.id === activeSessionId)?.title || "Agent d'Apprentissage"}
          </span>
        </header>

        {/* Chat window */}
        <div className="flex-1 overflow-hidden">
          {activeSessionId ? (
            <ChatWindow
              sessionId={activeSessionId}
              cachedMessages={messagesCache[activeSessionId]}
              onCacheMessages={cacheMessages}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-zinc-500">
              <MessageSquarePlus size={48} className="mb-4 opacity-30" />
              <p className="text-lg font-medium">Commence une conversation</p>
              <p className="text-sm mt-1">Cree une nouvelle session pour demarrer</p>
              <button
                onClick={handleNewSession}
                className="mt-4 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors"
              >
                + Nouvelle session
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
