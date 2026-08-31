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
  wikipedia: "Wikipédia",
  artifact: "Artefact",
  revision: "Révision",
  diagnostic: "Diagnostic",
};

/* Chaque méthode garde une teinte propre (l'information est réelle), mais
   réchauffée pour s'accorder au thème de la lampe. */
const METHOD_COLORS: Record<string, string> = {
  scaffold: "bg-primary-500/15 text-primary-400 border-primary-500/30",
  socratic: "bg-purple-500/15 text-purple-300 border-purple-500/30",
  feynman: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  quiz: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  web_search: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  wikipedia: "bg-teal-500/15 text-teal-300 border-teal-500/30",
  artifact: "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30",
  revision: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  diagnostic: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
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
            ? "bg-gradient-to-br from-primary-500 to-primary-600 text-zinc-950 shadow-lg shadow-primary-900/30"
            : "bg-surface-2 text-zinc-100 border border-zinc-700/50 shadow-lg shadow-black/20"
        }`}
      >
        {/* Halo discret de la lampe pour les réponses du tuteur */}
        {!isUser && (
          <div className="absolute inset-0 animate-glow-pulse pointer-events-none" />
        )}

        {/* Badge de méthode (tuteur uniquement) */}
        {!isUser && message.method && (
          <div className="mb-2 relative z-10">
            <span
              className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                METHOD_COLORS[message.method] || "bg-zinc-500/15 text-zinc-300 border-zinc-500/30"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-current opacity-70" />
              {METHOD_LABELS[message.method] || message.method}
            </span>
          </div>
        )}

        {/* Contenu */}
        <div className="text-sm leading-relaxed whitespace-pre-wrap relative z-10">
          {message.content}
        </div>

        {/* Horodatage */}
        <div
          className={`text-[11px] mt-1.5 relative z-10 ${
            isUser ? "text-zinc-950/60" : "text-zinc-500"
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
