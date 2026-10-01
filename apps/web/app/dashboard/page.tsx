"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  TrendingUp,
  BookOpen,
  AlertTriangle,
  CheckCircle2,
  ArrowUpRight,
  Sparkles,
  Target,
} from "lucide-react";
import { progress } from "@/lib/api";
import { AppShell, SidebarColumn } from "@/components/layout/AppShell";
import { NavSidebar } from "@/components/layout/NavSidebar";
import {
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const COLORS = ["#3b82f6", "#22c55e", "#eab308", "#ef4444", "#a855f7"];

type SummaryData = Awaited<ReturnType<typeof progress.summary>>;
type PlanItem = { competency: string; box: number; priority: string };
type PlanData = { plan: PlanItem[]; message?: string };

export default function DashboardPage() {
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [revisionPlan, setRevisionPlan] = useState<PlanData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      progress.summary().catch(() => null),
      progress.revisionPlan().catch(() => null),
    ]).then(([s, r]) => {
      setSummary(s);
      setRevisionPlan(r as PlanData | null);
      setLoading(false);
    });
  }, []);

  const masteredCount = summary?.acquired ?? 0;
  const gapsCount = Array.isArray(summary?.gaps) ? summary.gaps.length : 0;
  const totalCount = summary?.total_competencies ?? 0;
  const learningCount = Math.max(0, totalCount - masteredCount - gapsCount);

  const pieData = totalCount
    ? [
        { name: "Maîtrisées", value: masteredCount },
        { name: "En cours", value: learningCount },
        { name: "Lacunes", value: gapsCount },
      ].filter((d) => d.value > 0)
    : [];

  const planItems = Array.isArray(revisionPlan?.plan) ? revisionPlan.plan : [];

  return (
    <AppShell
      sidebar={
        <SidebarColumn>
          <NavSidebar active="/dashboard" />
        </SidebarColumn>
      }
    >
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-7xl p-5 sm:p-8">
          <header className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="eyebrow mb-2">Vue d&apos;ensemble</p>
              <h1 className="font-display text-3xl tracking-tight text-zinc-100 sm:text-4xl">Votre progression</h1>
              <p className="mt-2 max-w-xl text-sm leading-6 text-zinc-400">Un aperçu clair de vos acquis et des prochaines notions à consolider.</p>
            </div>
            <Link href="/chat" className="group inline-flex items-center gap-2 self-start rounded-lg bg-primary-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-primary-500/15 transition hover:bg-primary-400 sm:self-auto">
              <Sparkles size={16} />
              Démarrer une session
              <ArrowUpRight size={15} className="transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
            </Link>
          </header>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-28 rounded-xl bg-surface-1 animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            {/* KPI Cards */}
            <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
              <div className="dashboard-card rounded-2xl border border-zinc-800/80 bg-surface-1 p-5 transition hover:-translate-y-0.5 hover:border-zinc-700">
                <div className="mb-3 flex items-center gap-2 text-sm text-zinc-400">
                  <TrendingUp size={16} className="text-primary-400" />
                  Score moyen
                </div>
                <div className="text-3xl font-bold text-zinc-100">
                  {summary?.average_score
                    ? `${Math.round(summary.average_score * 100)}%`
                    : "—"}
                </div>
              </div>

              <div className="dashboard-card rounded-2xl border border-zinc-800/80 bg-surface-1 p-5 transition hover:-translate-y-0.5 hover:border-zinc-700">
                <div className="mb-3 flex items-center gap-2 text-sm text-zinc-400">
                  <CheckCircle2 size={16} className="text-emerald-400" />
                  Maîtrisées
                </div>
                <div className="text-3xl font-bold text-emerald-400">
                  {masteredCount}
                </div>
              </div>

              <div className="dashboard-card rounded-2xl border border-zinc-800/80 bg-surface-1 p-5 transition hover:-translate-y-0.5 hover:border-zinc-700">
                <div className="mb-3 flex items-center gap-2 text-sm text-zinc-400">
                  <BookOpen size={16} className="text-primary-400" />
                  En cours
                </div>
                <div className="text-3xl font-bold text-primary-400">
                  {learningCount}
                </div>
              </div>

              <div className="dashboard-card rounded-2xl border border-zinc-800/80 bg-surface-1 p-5 transition hover:-translate-y-0.5 hover:border-zinc-700">
                <div className="mb-3 flex items-center gap-2 text-sm text-zinc-400">
                  <AlertTriangle size={16} className="text-red-400" />
                  Lacunes
                </div>
                <div className="text-3xl font-bold text-red-400">
                  {gapsCount}
                </div>
              </div>
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Pie chart */}
              <section className="rounded-2xl border border-zinc-800/80 bg-surface-1 p-5">
                <div className="mb-5 flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-zinc-200">Répartition ({totalCount} compétences)</h2>
                  <Target size={17} className="text-zinc-500" />
                </div>
                {pieData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={250}>
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={90}
                        paddingAngle={5}
                        dataKey="value"
                      >
                        {pieData.map((_, index) => (
                          <Cell
                            key={index}
                            fill={COLORS[index % COLORS.length]}
                          />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          background: "#182030",
                          border: "1px solid #334155",
                          borderRadius: "8px",
                          color: "#f1f5f9",
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex min-h-60 flex-col items-center justify-center rounded-xl border border-dashed border-zinc-800 px-6 text-center">
                    <div className="mb-3 flex size-10 items-center justify-center rounded-full bg-primary-500/10 text-primary-400"><BookOpen size={18} /></div>
                    <p className="max-w-xs text-sm leading-6 text-zinc-400">Aucune compétence enregistrée pour l&apos;instant. Elles apparaîtront après vos sessions d&apos;apprentissage.</p>
                    <Link href="/chat" className="mt-4 text-sm font-semibold text-primary-400 hover:text-primary-300">Commencer à apprendre <ArrowUpRight size={14} className="ml-1 inline" /></Link>
                  </div>
                )}
              </section>

              {/* Revision plan */}
              <section className="rounded-2xl border border-zinc-800/80 bg-surface-1 p-5">
                <div className="mb-5 flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-zinc-200">Plan de révision</h2>
                  <Target size={17} className="text-zinc-500" />
                </div>
                {planItems.length > 0 ? (
                  <div className="space-y-2">
                    {planItems.slice(0, 6).map((item, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-2 rounded-lg bg-surface-2"
                      >
                        <span className="text-sm text-zinc-200">
                          {item.competency}
                        </span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full ${
                            item.priority === "high"
                              ? "bg-red-500/15 text-red-400"
                              : item.priority === "medium"
                              ? "bg-yellow-500/15 text-yellow-400"
                              : "bg-green-500/15 text-green-400"
                          }`}
                        >
                          {item.box}j
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500">
                    {revisionPlan?.message || "Aucun item à réviser"}
                  </p>
                )}
              </section>
            </div>
          </>
        )}
        </div>
      </main>
    </AppShell>
  );
}
