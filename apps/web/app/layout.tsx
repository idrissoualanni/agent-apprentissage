import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lueur — Agent d'Apprentissage",
  description:
    "Tuteur IA personnel : dialogue socratique, Feynman, quiz et répétition espacée. La lumière de la compréhension, session après session.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr" className="dark">
      <body className="h-screen overflow-hidden bg-surface-0 text-zinc-100 font-sans">
        {children}
      </body>
    </html>
  );
}
