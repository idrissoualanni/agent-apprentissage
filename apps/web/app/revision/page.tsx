"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { progress, type RevisionCalendarItem } from "@/lib/api";
import {
  Calendar,
  MessageSquare,
  LayoutDashboard,
  FileText,
  User,
  Cpu,
  Clock,
  CheckCircle2,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/revision", label: "Revision", icon: Calendar },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/profile", label: "Profil", icon: User },
  { href: "/models", label: "Modeles", icon: Cpu },
];

function formatDate(iso: string): string {
  try {
    return new Date(iso.replace(" ", "T")).toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function boxColor(box: number): string {
  if (box <= 1) return "bg-red-500/15 text-red-400";
  if (box <= 3) return "bg-yellow-500/15 text-yellow-400";
  return "bg-green-500/15 text-green-400";
}

export default function RevisionPage() {
  const [calendar, setCalendar] = useState<RevisionCalendarItem[]>([]);
  const [due, setDue] = useState<RevisionCalendarItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      progress.revisionCalendar().catch(() => []),
      progress.revisionDue().catch(() => []),
    ]).then(([cal, d]) => {
      setCalendar(cal);
      setDue(d);
      setLoading(false);
    });
  }, []);

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
            const isActive = item.href === "/revision";
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
        <h1 className="text-2xl font-bold mb-6">Calendrier de revision</h1>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 rounded-xl bg-surface-1 animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            {/* Revisions dues */}
            <div className="mb-8">
              <div className="flex items-center gap-2 mb-3">
                <Clock size={18} className="text-red-400" />
                <h2 className="text-lg font-semibold">A reviser maintenant</h2>
                <span className="text-sm text-zinc-500">({due.length})</span>
              </div>
              {due.length > 0 ? (
                <div className="space-y-2">
                  {due.map((item) => (
                    <div
                      key={item.competency_id}
                      className="flex items-center justify-between p-3 rounded-xl border border-red-500/30 bg-red-500/5"
                    >
                      <div>
                        <div className="text-sm font-medium text-zinc-100">{item.nom}</div>
                        <div className="text-xs text-zinc-500">{item.domain}</div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`text-xs px-2 py-0.5 rounded-full ${boxColor(item.leitner_box)}`}>
                          Boite {item.leitner_box}
                        </span>
                        <span className="text-xs text-red-400">
                          {formatDate(item.next_review_at)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-2 p-4 rounded-xl border border-zinc-800 bg-surface-1">
                  <CheckCircle2 size={18} className="text-emerald-400" />
                  <span className="text-sm text-zinc-400">Aucune revision due pour le moment.</span>
                </div>
              )}
            </div>

            {/* Calendrier complet */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Calendar size={18} className="text-blue-400" />
                <h2 className="text-lg font-semibold">Prochaines revisions</h2>
                <span className="text-sm text-zinc-500">({calendar.length})</span>
              </div>
              {calendar.length > 0 ? (
                <div className="rounded-xl border border-zinc-800 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-surface-1 text-zinc-400 text-xs uppercase">
                      <tr>
                        <th className="text-left p-3">Competence</th>
                        <th className="text-left p-3">Domaine</th>
                        <th className="text-left p-3">Maitrise</th>
                        <th className="text-left p-3">Boite</th>
                        <th className="text-left p-3">Prochaine revision</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800">
                      {calendar.map((item) => (
                        <tr key={item.competency_id} className="hover:bg-surface-1">
                          <td className="p-3 text-zinc-100">{item.nom}</td>
                          <td className="p-3 text-zinc-400">{item.domain}</td>
                          <td className="p-3">
                            <span className="text-zinc-200">
                              {Math.round((item.score || 0) * 100)}%
                            </span>
                          </td>
                          <td className="p-3">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${boxColor(item.leitner_box)}`}>
                              {item.leitner_box}
                            </span>
                          </td>
                          <td className="p-3 text-zinc-400">{formatDate(item.next_review_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-zinc-500">
                  Aucune revision planifiee. Les revisions apparaissent apres vos sessions d&apos;apprentissage.
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
