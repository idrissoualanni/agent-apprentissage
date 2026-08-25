"use client";

interface StreamingTextProps {
  text: string;
  method?: string;
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

export function StreamingText({ text, method }: StreamingTextProps) {
  return (
    <div className="flex justify-start animate-bubble-in">
      <div className="max-w-[80%] rounded-2xl px-4 py-3 bg-surface-2 border border-zinc-700/50 shadow-lg shadow-black/20 relative overflow-hidden">
        {/* Glow */}
        <div className="absolute inset-0 animate-glow-pulse pointer-events-none" />

        {method && (
          <div className="mb-2 relative z-10">
            <span
              className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full border ${
                METHOD_COLORS[method] || "bg-zinc-500/15 text-zinc-400 border-zinc-500/30"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-current opacity-70" />
              {METHOD_LABELS[method] || method}
            </span>
          </div>
        )}

        <div className="text-sm leading-relaxed whitespace-pre-wrap relative z-10">
          {text}
          {/* Animated cursor */}
          <span className="inline-flex items-center gap-0.5 ml-1 align-text-bottom">
            <span className="w-1 h-4 bg-primary-400 rounded-sm animate-pulse" />
          </span>
        </div>

        {/* Typing dots indicator */}
        <div className="flex items-center gap-1 mt-2 relative z-10">
          <div className="w-1.5 h-1.5 rounded-full bg-primary-400 animate-typing-dot" style={{ animationDelay: "0s" }} />
          <div className="w-1.5 h-1.5 rounded-full bg-primary-400 animate-typing-dot" style={{ animationDelay: "0.2s" }} />
          <div className="w-1.5 h-1.5 rounded-full bg-primary-400 animate-typing-dot" style={{ animationDelay: "0.4s" }} />
        </div>
      </div>
    </div>
  );
}
