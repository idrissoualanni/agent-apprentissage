"use client";

import type { ReactNode } from "react";

/**
 * Enveloppe commune de l'app : une colonne latérale + la zone principale.
 * Le contenu de la sidebar est injecté afin de laisser chaque page composer
 * la sienne (liste de sessions pour le chat, navigation seule ailleurs).
 */
export function AppShell({
  sidebar,
  children,
}: {
  sidebar: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex h-screen bg-surface-0">
      {sidebar}
      <div className="flex-1 flex flex-col min-w-0">{children}</div>
    </div>
  );
}

/** Colonne latérale standard : largeur fixe, filet à droite, fond surface-1. */
export function SidebarColumn({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <aside
      className={`w-64 shrink-0 flex flex-col border-r border-zinc-800 bg-surface-1 ${className}`}
    >
      {children}
    </aside>
  );
}
