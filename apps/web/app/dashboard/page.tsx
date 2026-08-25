"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { progress } from "@/lib/api";
import type { ProgressSummary, RevisionPlan as RevisionPlanType } from "@/lib/types";
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  User,
  Cpu,
  TrendingUp,
  BookOpen,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const NAV_ITEMS = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/profile", label: "Profil", icon: User },
  { href: "/models", label: "Modeles", icon: Cpu },
];

const COLORS = ["#3b82f6", "#22c55e", "#eab308", "#ef4444", "#a855f7"];

export default function DashboardPage() {
  const [summary, setSummary] = useState<ProgressSummary | null>(null);
  const [revisionPlan, setRevisionPlan] = useState<RevisionPlanType | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      progress.overview().catch(() => null),
      progress.revisionPlan().catch(() => null),
    ]).then(([s, r]) => {
      setSummary(s);
      setRevisionPlan(r);
      setLoading(false);
    });
  }, []);

  const pieData = summary
    ? [
        { name: "Maitrise", value: summary.mastered?.length || 0 },
        { name: "En cours", value: summary.total - (summary.mastered?.length || 0) - (summary.gaps?.length || 0) },
        { name: "Lacunes", value: summary.gaps?.length || 0 },
      ]
    : [];

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
            const isActive = item.href === "/dashboard";
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
      <div className="flex-1 overflow-y-auto p-6">
        <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

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
                  {summary?.average_score ? `${Math.round(summary.average_score * 100)}%` : "—"}
                </div>
              </div>

              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <div className="flex items-center gap-2 text-zinc-400 text-sm mb-2">
                  <CheckCircle2 size={16} />
                  Maitrisees
                </div>
                <div className="text-3xl font-bold text-emerald-400">
                  {summary?.mastered?.length || 0}
                </div>
              </div>

              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <div className="flex items-center gap-2 text-zinc-400 text-sm mb-2">
                  <BookOpen size={16} />
                  En cours
                </div>
                <div className="text-3xl font-bold text-blue-400">
                  {summary ? summary.total - (summary.mastered?.length || 0) - (summary.gaps?.length || 0) : 0}
                </div>
              </div>

              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <div className="flex items-center gap-2 text-zinc-400 text-sm mb-2">
                  <AlertTriangle size={16} />
                  Lacunes
                </div>
                <div className="text-3xl font-bold text-red-400">
                  {summary?.gaps?.length || 0}
                </div>
              </div>
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Pie chart */}
              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <h3 className="text-sm font-medium text-zinc-400 mb-4">Repartition</h3>
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
                        <Cell key={index} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "#27272a",
                        border: "1px solid #3f3f46",
                        borderRadius: "8px",
                        color: "#fafafa",
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Revision plan */}
              <div className="rounded-xl border border-zinc-800 bg-surface-1 p-4">
                <h3 className="text-sm font-medium text-zinc-400 mb-4">Plan de revision</h3>
                {revisionPlan && revisionPlan.plan.length > 0 ? (
                  <div className="space-y-2">
                    {revisionPlan.plan.slice(0, 6).map((item, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-2 rounded-lg bg-surface-2"
                      >
                        <span className="text-sm text-zinc-200">{item.competency}</span>
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
                  <p className="text-sm text-zinc-500">Aucun item a reviser</p>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
