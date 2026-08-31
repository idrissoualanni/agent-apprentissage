"use client";

import { useState, useEffect } from "react";
import {
  TrendingUp,
  BookOpen,
  AlertTriangle,
  CheckCircle2,
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
      <div className="flex-1 overflow-y-auto p-6">
        <h1 className="text-2xl font-bold mb-6">Tableau de bord</h1>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-28 rounded-xl bg-surface-1 animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <div className="flex items-center gap-2 text-zinc-400 text-sm mb-2">
                  <TrendingUp size={16} />
                  Score moyen
                </div>
                <div className="text-3xl font-bold text-zinc-100">
                  {summary?.average_score
                    ? `${Math.round(summary.average_score * 100)}%`
                    : "—"}
                </div>
              </div>

              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <div className="flex items-center gap-2 text-zinc-400 text-sm mb-2">
                  <CheckCircle2 size={16} />
                  Maîtrisées
                </div>
                <div className="text-3xl font-bold text-emerald-400">
                  {masteredCount}
                </div>
              </div>

              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <div className="flex items-center gap-2 text-zinc-400 text-sm mb-2">
                  <BookOpen size={16} />
                  En cours
                </div>
                <div className="text-3xl font-bold text-primary-400">
                  {learningCount}
                </div>
              </div>

              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <div className="flex items-center gap-2 text-zinc-400 text-sm mb-2">
                  <AlertTriangle size={16} />
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
              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <h3 className="text-sm font-medium text-zinc-400 mb-4">
                  Répartition ({totalCount} compétences)
                </h3>
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
                  <p className="text-sm text-zinc-500 py-8 text-center">
                    Aucune compétence enregistrée pour l&apos;instant.
                    <br />
                    Elles apparaîtront après vos sessions d&apos;apprentissage.
                  </p>
                )}
              </div>

              {/* Revision plan */}
              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <h3 className="text-sm font-medium text-zinc-400 mb-4">
                  Plan de révision
                </h3>
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
              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
