"use client";

import { useState } from "react";
import type { ToolUsage } from "@/lib/types";
import { ChevronDown, ChevronUp, Zap } from "lucide-react";

interface ToolBadgeProps {
  tools: ToolUsage[];
}

const TOOL_LABELS: Record<string, string> = {
  rag_retrieval: "RAG",
  generate_quiz: "Quiz",
  evaluate_feynman: "Feynman",
  create_artifact: "Artefact",
  web_search: "Recherche web",
  wikipedia_search: "Wikipédia",
  update_mastery: "Maîtrise",
  revision_plan: "Révision",
};

const TOOL_COLORS: Record<string, string> = {
  rag_retrieval: "text-teal-300",
  generate_quiz: "text-emerald-300",
  evaluate_feynman: "text-rose-300",
  create_artifact: "text-fuchsia-300",
  web_search: "text-sky-300",
  wikipedia_search: "text-teal-300",
  update_mastery: "text-orange-300",
  revision_plan: "text-purple-300",
};

const TOOL_BG: Record<string, string> = {
  rag_retrieval: "bg-teal-500/10",
  generate_quiz: "bg-emerald-500/10",
  evaluate_feynman: "bg-rose-500/10",
  create_artifact: "bg-fuchsia-500/10",
  web_search: "bg-sky-500/10",
  wikipedia_search: "bg-teal-500/10",
  update_mastery: "bg-orange-500/10",
  revision_plan: "bg-purple-500/10",
};

export function ToolBadge({ tools }: ToolBadgeProps) {
  const [expanded, setExpanded] = useState(false);
  const totalDuration = tools.reduce((sum, t) => sum + t.duration_ms, 0);

  if (tools.length === 0) return null;

  return (
    <div className="flex justify-start ml-12 mt-1 animate-fade-in">
      <div className="rounded-xl border border-zinc-800/80 bg-surface-1/80 backdrop-blur-sm overflow-hidden">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-300 hover:bg-surface-2/50 transition-all duration-200 w-full"
        >
          <Zap size={12} className="text-primary-400" />
          <span className="font-medium">
            {tools.length} outil{tools.length > 1 ? "s" : ""}
          </span>
          {totalDuration > 0 && (
            <span className="text-zinc-600 font-mono text-[10px]">
              {Math.round(totalDuration)}ms
            </span>
          )}
          <span className="ml-auto">
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </span>
        </button>

        {expanded && (
          <div className="border-t border-zinc-800/80 px-3 py-2 space-y-1">
            {tools.map((tool, i) => (
              <div
                key={i}
                className="flex items-center gap-2 text-xs py-0.5 px-2 rounded-md hover:bg-surface-2/50 transition-colors"
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    TOOL_COLORS[tool.tool] || "text-zinc-400"
                  } bg-current opacity-70`}
                />
                <span className={TOOL_COLORS[tool.tool] || "text-zinc-400"}>
                  {TOOL_LABELS[tool.tool] || tool.tool}
                </span>
                {tool.duration_ms > 0 && (
                  <span className="text-zinc-600 font-mono text-[10px] ml-auto">
                    {Math.round(tool.duration_ms)}ms
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
