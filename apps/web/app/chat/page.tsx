"use client";

import { useState, useEffect, useCallback } from "react";
import { SessionList } from "@/components/sidebar/SessionList";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { AppShell, SidebarColumn } from "@/components/layout/AppShell";
import { NavSidebar, Brand } from "@/components/layout/NavSidebar";
import { sessions as sessionsAPI } from "@/lib/api";
import type { Session, ChatMessage } from "@/lib/types";
import {
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  LampDesk,
} from "lucide-react";

export default function ChatPage() {
  const [sessionList, setSessionList] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [loading, setLoading] = useState(true);
  // Cache des messages par session : le changement de session est instantane
  // pour une session deja chargee (pas de re-appel reseau).
  const [messagesCache, setMessagesCache] = useState<Record<number, ChatMessage[]>>({});

  // Chargement UNIQUE au montage.
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

  const activeTitle =
    sessionList.find((s) => s.id === activeSessionId)?.title || "Nouvelle session";

  return (
    <AppShell
      sidebar={
        sidebarOpen ? (
          <SidebarColumn>
            <Brand />
            <div className="mx-3 border-t border-zinc-800/70" />

            {/* En-tête sessions */}
            <div className="flex items-center justify-between px-3 pt-3 pb-2">
              <span className="eyebrow">Sessions</span>
              <button
                onClick={handleNewSession}
                className="p-1.5 rounded-md hover:bg-surface-2 text-zinc-400 hover:text-primary-400 transition-colors"
                title="Nouvelle session"
                aria-label="Nouvelle session"
              >
                <MessageSquarePlus size={16} />
              </button>
            </div>

            {/* Liste des sessions */}
            <div className="flex-1 overflow-y-auto px-1">
              <SessionList
                sessions={sessionList}
                activeId={activeSessionId}
                onSelect={setActiveSessionId}
                onDelete={handleDeleteSession}
                loading={loading}
              />
            </div>

            {/* Navigation */}
            <div className="border-t border-zinc-800/70">
              <NavSidebar active="/chat" showBrand={false} />
            </div>
          </SidebarColumn>
        ) : null
      }
    >
      {/* Barre supérieure */}
      <header className="flex items-center gap-3 h-14 px-4 border-b border-zinc-800 bg-surface-1/60 backdrop-blur-sm">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-1.5 rounded-md hover:bg-surface-2 text-zinc-400 hover:text-zinc-200 transition-colors"
          aria-label={sidebarOpen ? "Masquer le panneau" : "Afficher le panneau"}
        >
          {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
        </button>
        <div className="min-w-0">
          <div className="eyebrow">Session</div>
          <div className="text-sm font-semibold text-zinc-100 truncate">{activeTitle}</div>
        </div>
      </header>

      {/* Fenêtre de chat */}
      <div className="flex-1 overflow-hidden">
        {activeSessionId ? (
          <ChatWindow
            sessionId={activeSessionId}
            cachedMessages={messagesCache[activeSessionId]}
            onCacheMessages={cacheMessages}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <div className="w-14 h-14 rounded-2xl bg-primary-500/15 border border-primary-500/30 flex items-center justify-center lamp-glow mb-5">
              <LampDesk size={26} className="text-primary-400" />
            </div>
            <p className="font-display text-2xl text-zinc-100">Allume ta première session</p>
            <p className="text-sm text-zinc-500 mt-2 max-w-sm">
              Crée une session et pose ta question — le tuteur s&apos;adapte à ton niveau,
              entre dialogue, quiz et Feynman.
            </p>
            <button
              onClick={handleNewSession}
              className="mt-6 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 text-zinc-950 rounded-lg text-sm font-bold transition-colors"
            >
              Nouvelle session
            </button>
          </div>
        )}
      </div>
    </AppShell>
  );
}
