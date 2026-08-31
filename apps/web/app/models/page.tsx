"use client";

import { useState, useEffect } from "react";
import { models } from "@/lib/api";
import type { ModelConfig } from "@/lib/types";
import {
  Check,
  Cloud,
  HardDrive,
} from "lucide-react";
import { AppShell, SidebarColumn } from "@/components/layout/AppShell";
import { NavSidebar } from "@/components/layout/NavSidebar";

export default function ModelsPage() {
  const [catalog, setCatalog] = useState<ModelConfig[]>([]);
  const [activeModels, setActiveModels] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [selecting, setSelecting] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      models.catalog().catch(() => []),
      models.active().catch(() => ({})),
    ]).then(([c, a]) => {
      setCatalog(c);
      setActiveModels(a);
      setLoading(false);
    });
  }, []);

  const handleSelect = async (operation: string, modelName: string) => {
    setSelecting(`${operation}-${modelName}`);
    try {
      await models.select(operation, modelName);
      setActiveModels((prev) => ({ ...prev, [operation]: modelName }));
    } catch (err) {
      console.error("Failed to select model:", err);
    } finally {
      setSelecting(null);
    }
  };

  const OPERATIONS = [
    { key: "chat", label: "Chat", description: "Reponses generales" },
    { key: "quiz_generation", label: "Quiz", description: "Generation de quiz" },
    { key: "feynman_eval", label: "Feynman", description: "Evaluation Feynman" },
    { key: "artifact", label: "Artefacts", description: "Creation d'artefacts" },
    { key: "diagnostic", label: "Diagnostic", description: "Estimation niveau" },
  ];

  return (
    <AppShell
      sidebar={
        <SidebarColumn>
          <NavSidebar active="/models" />
        </SidebarColumn>
      }
    >
      <div className="flex-1 overflow-y-auto p-6 max-w-4xl">
        <h1 className="text-2xl font-bold mb-6">Gestion des Modeles</h1>

        {loading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 rounded-xl bg-surface-1 animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            {/* Active models by operation */}
            <div className="mb-8">
              <h2 className="text-sm font-medium text-zinc-400 mb-4">Modeles actifs par operation</h2>
              <div className="space-y-2">
                {OPERATIONS.map((op) => (
                  <div
                    key={op.key}
                    className="flex items-center justify-between p-4 rounded-xl border border-zinc-800 bg-surface-1"
                  >
                    <div>
                      <p className="text-sm font-medium text-zinc-200">{op.label}</p>
                      <p className="text-xs text-zinc-500">{op.description}</p>
                    </div>
                    <span className="text-sm text-primary-400 font-mono">
                      {activeModels[op.key] || "—"}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Catalog */}
            <div>
              <h2 className="text-sm font-medium text-zinc-400 mb-4">Catalogue</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {catalog.map((model) => (
                  <div
                    key={model.model_name}
                    className="p-4 rounded-xl border border-zinc-800 bg-surface-1"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {model.provider === "ollama_cloud" ? (
                          <Cloud size={16} className="text-blue-400" />
                        ) : (
                          <HardDrive size={16} className="text-emerald-400" />
                        )}
                        <span className="text-sm font-medium text-zinc-200">
                          {model.display_name}
                        </span>
                      </div>
                      {model.is_active && (
                        <Check size={14} className="text-emerald-400" />
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-zinc-500 mb-3">
                      <span>{model.provider}</span>
                      <span>{model.format_mode}</span>
                      <span>temp {model.default_temperature}</span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {OPERATIONS.filter((op) => op.key !== "diagnostic").map((op) => (
                        <button
                          key={op.key}
                          onClick={() => handleSelect(op.key, model.model_name)}
                          disabled={selecting === `${op.key}-${model.model_name}`}
                          className={`px-2 py-1 text-xs rounded-md border transition-colors ${
                            activeModels[op.key] === model.model_name
                              ? "border-primary-500 bg-primary-500/15 text-primary-400"
                              : "border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300"
                          } ${selecting === `${op.key}-${model.model_name}` ? "opacity-50" : ""}`}
                        >
                          {op.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
