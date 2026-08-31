"use client";

import Link from "next/link";
import {
  MessageSquare,
  LayoutDashboard,
  CalendarClock,
  FileText,
  User,
  Cpu,
  LampDesk,
} from "lucide-react";

export const NAV_ITEMS = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard },
  { href: "/revision", label: "Révision", icon: CalendarClock },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/profile", label: "Profil", icon: User },
  { href: "/models", label: "Modèles", icon: Cpu },
];

/** Marque « Lueur » — la lampe du tuteur. */
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`flex items-center gap-2.5 px-3 ${compact ? "py-3" : "py-4"}`}>
      <div className="w-9 h-9 rounded-xl bg-primary-500/15 border border-primary-500/30 flex items-center justify-center lamp-glow">
        <LampDesk size={18} className="text-primary-400" />
      </div>
      <div className="min-w-0">
        <div className="font-display text-lg leading-none text-zinc-100 tracking-tight">
          Lueur
        </div>
        <div className="text-[11px] text-zinc-500 mt-0.5 truncate">
          Agent d&apos;apprentissage
        </div>
      </div>
    </div>
  );
}

/**
 * Navigation latérale partagée. Indique la page active d'un filet ambre sur la
 * gauche — la lumière guide d'une section à l'autre.
 */
export function NavSidebar({
  active,
  showBrand = true,
  className = "",
}: {
  active: string;
  showBrand?: boolean;
  className?: string;
}) {
  return (
    <nav className={`flex flex-col ${className}`}>
      {showBrand && <Brand />}
      {showBrand && <div className="mx-3 border-t border-zinc-800/70" />}
      <div className="p-2 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = item.href === active;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={`relative flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-primary-500/10 text-primary-400 font-semibold"
                  : "text-zinc-400 hover:bg-surface-2 hover:text-zinc-200"
              }`}
            >
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r bg-primary-500" />
              )}
              <Icon size={16} className={isActive ? "text-primary-400" : ""} />
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
