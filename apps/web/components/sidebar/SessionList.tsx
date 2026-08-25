"use client";

import type { Session } from "@/lib/types";
import { Trash2, MessageSquare } from "lucide-react";

interface SessionListProps {
  sessions: Session[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
  loading: boolean;
}

export function SessionList({
  sessions,
  activeId,
  onSelect,
  onDelete,
  loading,
}: SessionListProps) {
  if (loading) {
    return (
      <div className="p-4 space-y-2">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-10 rounded-lg bg-surface-2 animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="p-4 text-center text-zinc-500 text-sm">
        Aucune session
      </div>
    );
  }

  return (
    <div className="p-2 space-y-0.5">
      {sessions.map((session) => (
        <div
          key={session.id}
          onClick={() => onSelect(session.id)}
          className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
            session.id === activeId
              ? "bg-surface-2 text-zinc-100"
              : "text-zinc-400 hover:bg-surface-2/50 hover:text-zinc-200"
          }`}
        >
          <MessageSquare size={14} className="flex-shrink-0 opacity-50" />
          <span className="flex-1 text-sm truncate">
            {session.title || `Session ${session.id}`}
          </span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete(session.id);
            }}
            className="p-1 rounded hover:bg-red-500/20 text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
          >
            <Trash2 size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}
