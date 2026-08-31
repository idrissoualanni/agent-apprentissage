"use client";

import type { Artifact } from "@/lib/types";
import { QuizArtifact } from "./QuizArtifact";

interface ArtifactRendererProps {
  artifact: Artifact;
  sessionId?: number;
}

export function ArtifactRenderer({ artifact, sessionId }: ArtifactRendererProps) {
  switch (artifact.artifact_type) {
    case "quiz":
      return (
        <QuizArtifact
          title={artifact.title}
          content={artifact.content}
          metadata={artifact.metadata}
          sessionId={sessionId}
        />
      );
    case "schema":
      return <SchemaArtifact title={artifact.title} content={artifact.content} />;
    case "code":
      return <CodeArtifact title={artifact.title} content={artifact.content} />;
    case "chart":
      return <ChartArtifact title={artifact.title} content={artifact.content} />;
    default:
      return (
        <div className="p-4 text-sm text-zinc-400">
          Type d'artefact inconnu: {artifact.artifact_type}
        </div>
      );
  }
}

function SchemaArtifact({ title, content }: { title: string; content: string }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-surface-1 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800 bg-surface-2">
        <span className="text-xs text-fuchsia-300 font-medium">Schéma</span>
        <span className="text-xs text-zinc-500">{title}</span>
      </div>
      <div className="p-4">
        <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-mono bg-surface-0 rounded-lg p-3 overflow-x-auto">
          {content}
        </pre>
      </div>
    </div>
  );
}

function CodeArtifact({ title, content }: { title: string; content: string }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-surface-1 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800 bg-surface-2">
        <span className="text-xs text-emerald-300 font-medium">Code</span>
        <span className="text-xs text-zinc-500">{title}</span>
      </div>
      <pre className="p-4 text-sm text-zinc-300 font-mono bg-surface-0 overflow-x-auto">
        {content}
      </pre>
    </div>
  );
}

function ChartArtifact({ title, content }: { title: string; content: string }) {
  let chartData: Record<string, unknown> | null = null;
  try {
    chartData = JSON.parse(content);
  } catch {
    // fallback
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-surface-1 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800 bg-surface-2">
        <span className="text-xs text-sky-300 font-medium">Graphique</span>
        <span className="text-xs text-zinc-500">{title}</span>
      </div>
      <div className="p-4">
        {chartData ? (
          <pre className="text-xs text-zinc-400 font-mono bg-surface-0 rounded-lg p-3 overflow-x-auto">
            {JSON.stringify(chartData, null, 2)}
          </pre>
        ) : (
          <pre className="text-sm text-zinc-300 whitespace-pre-wrap">{content}</pre>
        )}
      </div>
    </div>
  );
}
