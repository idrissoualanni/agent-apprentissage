"use client";

import { useState, useEffect } from "react";
import type { ChatMessage } from "@/lib/types";

interface MessageBubbleProps {
  message: ChatMessage;
}

const METHOD_LABELS: Record<string, string> = {
  scaffold: "Scaffold",
  socratic: "Socratique",
  feynman: "Feynman",
  quiz: "Quiz",
  web_search: "Web",
  artifact: "Artefact",
  revision: "Revision",
  diagnostic: "Diagnostic",
};

const METHOD_COLORS: Record<string, string> = {
  scaffold: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  socratic: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  feynman: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  quiz: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  web_search: "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
  artifact: "bg-pink-500/15 text-pink-400 border-pink-500/30",
  revision: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  diagnostic: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
};

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 50);
    return () => clearTimeout(t);
  }, []);

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} group ${
        visible
          ? isUser
            ? "animate-bubble-user"
            : "animate-bubble-in"
          : "opacity-0"
      }`}
    >
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 relative overflow-hidden ${
          isUser
            ? "bg-primary-600 text-white shadow-lg shadow-primary-600/20"
            : "bg-surface-2 text-zinc-100 border border-zinc-700/50 shadow-lg shadow-black/20"
        }`}
      >
        {/* Subtle glow effect for assistant */}
        {!isUser && (
          <div className="absolute inset-0 animate-glow-pulse pointer-events-none" />
        )}

        {/* Method badge (assistant only) */}
        {!isUser && message.method && (
          <div className="mb-2 relative z-10">
            <span
              className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full border ${
                METHOD_COLORS[message.method] || "bg-zinc-500/15 text-zinc-400 border-zinc-500/30"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-current opacity-70" />
              {METHOD_LABELS[message.method] || message.method}
            </span>
          </div>
        )}

        {/* Message content */}
        <div className="text-sm leading-relaxed whitespace-pre-wrap relative z-10">
          {message.content}
        </div>

        {/* Timestamp */}
        <div
          className={`text-[11px] mt-1.5 relative z-10 ${
            isUser ? "text-blue-200/50" : "text-zinc-500"
          }`}
        >
          {new Date(message.created_at).toLocaleTimeString("fr-FR", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      </div>
    </div>
  );
}
