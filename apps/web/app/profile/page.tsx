"use client";

import { useState, useEffect } from "react";
import { profile, progress } from "@/lib/api";
import type { LearnerProfile, CompetencyMastery } from "@/lib/types";
import {
  Save,
  CheckCircle2,
  AlertTriangle,
  BookOpen,
} from "lucide-react";
import { AppShell, SidebarColumn } from "@/components/layout/AppShell";
import { NavSidebar } from "@/components/layout/NavSidebar";

function MasteryBar({ item }: { item: CompetencyMastery }) {
  const pct = Math.round(item.score * 100);
  const color =
    item.score >= 0.7
      ? "bg-emerald-500"
      : item.score >= 0.4
      ? "bg-blue-500"
      : "bg-red-500";

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-zinc-200 w-40 truncate">{item.nom}</span>
      <div className="flex-1 h-2 bg-surface-3 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-zinc-400 w-10 text-right">{pct}%</span>
    </div>
  );
}

export default function ProfilePage() {
  const [data, setData] = useState<LearnerProfile | null>(null);
  const [summary, setSummary] = useState<{
    total_competencies: number;
    average_score: number;
    acquired: number;
    learning: number;
    new: number;
    gaps: { id: number; nom: string; score: number }[];
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [domain, setDomain] = useState("");
  const [niveau, setNiveau] = useState("");
  const [learningContext, setLearningContext] = useState("");
  const [goals, setGoals] = useState("");

  useEffect(() => {
    profile
      .get()
      .then((p) => {
        setData(p);
        setDomain(p.domain || "");
        setNiveau(p.niveau_global || "");
        setLearningContext(p.learning_context || "");
        setGoals(p.goals || "");
      })
      .catch(console.error);
    progress
      .summary()
      .then(setSummary)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await profile.update({
        domain,
        niveau_global: niveau,
        learning_context: learningContext,
        goals,
      });
    } catch (err) {
      console.error("Save failed:", err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppShell
      sidebar={
        <SidebarColumn>
          <NavSidebar active="/profile" />
        </SidebarColumn>
      }
    >
      <div className="flex-1 overflow-y-auto p-6 max-w-3xl">
        <h1 className="text-2xl font-bold mb-6">Profil d&apos;apprentissage</h1>

        {loading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 rounded-xl bg-surface-1 animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            {/* Basic info */}
            <div className="rounded-xl border border-zinc-800 bg-surface-1 p-5 mb-6">
              <h2 className="text-sm font-medium text-zinc-400 mb-4">Informations</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Domaine</label>
                  <input
                    value={domain}
                    onChange={(e) => setDomain(e.target.value)}
                    placeholder="Ex: Python, Developpement Web..."
                    className="w-full px-3 py-2 rounded-lg bg-surface-2 border border-zinc-700 text-sm text-zinc-100 placeholder-zinc-500 focus:border-primary-500 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Niveau global</label>
                  <select
                    value={niveau}
                    onChange={(e) => setNiveau(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-surface-2 border border-zinc-700 text-sm text-zinc-100 focus:border-primary-500 outline-none"
                  >
                    <option value="">Non defini</option>
                    <option value="debutant">Debutant</option>
                    <option value="intermediaire">Intermediaire</option>
                    <option value="avance">Avance</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Contexte d'apprentissage</label>
                  <textarea
                    value={learningContext}
                    onChange={(e) => setLearningContext(e.target.value)}
                    placeholder="Decris ton parcours, ton experience..."
                    rows={3}
                    className="w-full px-3 py-2 rounded-lg bg-surface-2 border border-zinc-700 text-sm text-zinc-100 placeholder-zinc-500 focus:border-primary-500 outline-none resize-none"
                  />
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Objectifs</label>
                  <textarea
                    value={goals}
                    onChange={(e) => setGoals(e.target.value)}
                    placeholder="Que veux-tu apprendre ?"
                    rows={2}
                    className="w-full px-3 py-2 rounded-lg bg-surface-2 border border-zinc-700 text-sm text-zinc-100 placeholder-zinc-500 focus:border-primary-500 outline-none resize-none"
                  />
                </div>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
                >
                  <Save size={14} />
                  {saving ? "Sauvegarde..." : "Sauvegarder"}
                </button>
              </div>
            </div>

            {/* Competencies breakdown — vraies donnees de /progress/summary */}
            {summary && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                {/* Mastered */}
                <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                  <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium mb-3">
                    <CheckCircle2 size={16} />
                    Maîtrisées ({summary.acquired ?? 0})
                  </div>
                  <p className="text-xs text-zinc-600">
                    {summary.acquired
                      ? "Compétences acquises (score ≥ 70%)"
                      : "Aucune pour l'instant"}
                  </p>
                </div>

                {/* Learning */}
                <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                  <div className="flex items-center gap-2 text-primary-400 text-sm font-medium mb-3">
                    <BookOpen size={16} />
                    En cours ({summary.learning ?? 0})
                  </div>
                  <p className="text-xs text-zinc-600">
                    {summary.learning
                      ? "Compétences en apprentissage"
                      : "Aucune pour l'instant"}
                  </p>
                </div>

                {/* Gaps */}
                <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                  <div className="flex items-center gap-2 text-red-400 text-sm font-medium mb-3">
                    <AlertTriangle size={16} />
                    À travailler ({Array.isArray(summary.gaps) ? summary.gaps.length : 0})
                  </div>
                  <div className="space-y-2 max-h-40 overflow-y-auto">
                    {(summary.gaps || []).slice(0, 10).map((c) => (
                      <MasteryBar
                        key={c.id}
                        item={{
                          competency_id: c.id,
                          nom: c.nom,
                          score: c.score,
                          status: "gap",
                          box: 0,
                        }}
                      />
                    ))}
                    {(!summary.gaps || summary.gaps.length === 0) && (
                      <p className="text-xs text-zinc-600">Aucune</p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Score */}
            {summary && (
              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-zinc-400">
                    Score moyen ({summary.total_competencies} compétences)
                  </span>
                  <span className="text-2xl font-bold text-zinc-100">
                    {summary.average_score
                      ? `${Math.round(summary.average_score * 100)}%`
                      : "—"}
                  </span>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
