import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent d'Apprentissage",
  description: "Tuteur IA personnel avec quiz, Feynman et RAG",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr" className="dark">
      <body className="h-screen overflow-hidden bg-surface-0 text-zinc-100">
        {children}
      </body>
    </html>
  );
}
