"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { profile } from "@/lib/api";
import type { LearnerProfile, CompetencyMastery } from "@/lib/types";
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  User,
  Cpu,
  Save,
  CheckCircle2,
  AlertTriangle,
  BookOpen,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/profile", label: "Profil", icon: User },
  { href: "/models", label: "Modeles", icon: Cpu },
];

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
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="w-64 flex flex-col border-r border-zinc-800 bg-surface-1">
        <div className="p-3 border-b border-zinc-800">
          <span className="text-sm font-medium text-zinc-400">Navigation</span>
        </div>
        <div className="flex-1 p-2 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = item.href === "/profile";
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

      {/* Main */}
      <div className="flex-1 overflow-y-auto p-6 max-w-3xl">
        <h1 className="text-2xl font-bold mb-6">Profil d'apprentissage</h1>

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

            {/* Competencies breakdown */}
            {data && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                {/* Mastered */}
                <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                  <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium mb-3">
                    <CheckCircle2 size={16} />
                    Maitrisees ({data.mastered_competencies?.length || 0})
                  </div>
                  <div className="space-y-2">
                    {data.mastered_competencies?.map((c) => (
                      <MasteryBar key={c.competency_id} item={c} />
                    ))}
                    {(!data.mastered_competencies || data.mastered_competencies.length === 0) && (
                      <p className="text-xs text-zinc-600">Aucune</p>
                    )}
                  </div>
                </div>

                {/* Learning */}
                <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                  <div className="flex items-center gap-2 text-blue-400 text-sm font-medium mb-3">
                    <BookOpen size={16} />
                    En cours ({data.learning_competencies?.length || 0})
                  </div>
                  <div className="space-y-2">
                    {data.learning_competencies?.map((c) => (
                      <MasteryBar key={c.competency_id} item={c} />
                    ))}
                    {(!data.learning_competencies || data.learning_competencies.length === 0) && (
                      <p className="text-xs text-zinc-600">Aucune</p>
                    )}
                  </div>
                </div>

                {/* Gaps */}
                <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                  <div className="flex items-center gap-2 text-red-400 text-sm font-medium mb-3">
                    <AlertTriangle size={16} />
                    Lacunes ({data.gaps?.length || 0})
                  </div>
                  <div className="space-y-2">
                    {data.gaps?.map((c) => (
                      <MasteryBar key={c.competency_id} item={c} />
                    ))}
                    {(!data.gaps || data.gaps.length === 0) && (
                      <p className="text-xs text-zinc-600">Aucune</p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Score */}
            {data && (
              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-zinc-400">Score moyen</span>
                  <span className="text-2xl font-bold text-zinc-100">
                    {data.average_score ? `${Math.round(data.average_score * 100)}%` : "—"}
                  </span>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
