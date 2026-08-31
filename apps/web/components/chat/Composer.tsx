"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Plus, Globe, FileText, Upload, X, Check } from "lucide-react";
import { documents } from "@/lib/api";

interface ComposerProps {
  onSend: (question: string, forceWebSearch: boolean) => void;
  disabled?: boolean;
}

/**
 * Barre de saisie du chat avec :
 *  - Bouton "+" (popover d'upload de PDF)
 *  - Textarea
 *  - Toggle "Recherche web"
 *  - Bouton Envoyer
 */
export function Composer({ onSend, disabled = false }: ComposerProps) {
  const [input, setInput] = useState("");
  const [webSearch, setWebSearch] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const menuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Fermer le popover quand on clique ailleurs
  useEffect(() => {
    if (!menuOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  // Auto-dismiss du statut d'upload
  useEffect(() => {
    if (!uploadStatus) return;
    const t = setTimeout(() => setUploadStatus(null), 4000);
    return () => clearTimeout(t);
  }, [uploadStatus]);

  const handleSend = useCallback(() => {
    const question = input.trim();
    if (!question || disabled) return;
    setInput("");
    onSend(question, webSearch);
    // Garder le focus dans le textarea après envoi
    textareaRef.current?.focus();
  }, [input, disabled, onSend, webSearch]);

  const handleFileSelect = useCallback(
    async (file: File) => {
      setMenuOpen(false);
      if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
        setUploadStatus({ type: "error", message: "Seuls les fichiers PDF sont acceptés." });
        return;
      }
      setUploading(true);
      setUploadStatus(null);
      try {
        await documents.upload(file);
        setUploadStatus({
          type: "success",
          message: `"${file.name}" importé. Il sera indexé pour le RAG.`,
        });
      } catch (err) {
        setUploadStatus({
          type: "error",
          message: err instanceof Error ? err.message : "Échec de l'upload.",
        });
      } finally {
        setUploading(false);
      }
    },
    []
  );

  return (
    <div className="border-t border-zinc-800 bg-surface-1/50 p-4">
      <div className="max-w-3xl mx-auto">
        {/* Bandeau de statut d'upload */}
        {uploadStatus && (
          <div
            className={`mb-2 flex items-center gap-2 rounded-lg px-3 py-2 text-xs ${
              uploadStatus.type === "success"
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                : "bg-red-500/10 text-red-400 border border-red-500/20"
            }`}
          >
            {uploadStatus.type === "success" ? <Check size={14} /> : <X size={14} />}
            <span className="flex-1">{uploadStatus.message}</span>
            <button
              onClick={() => setUploadStatus(null)}
              className="opacity-60 hover:opacity-100 transition-opacity"
            >
              <X size={12} />
            </button>
          </div>
        )}

        {/* Indicateur recherche web active */}
        {webSearch && (
          <div className="mb-2 flex items-center gap-1.5 text-xs text-primary-400">
            <Globe size={13} />
            <span>Recherche web activée pour ce message</span>
          </div>
        )}

        <div className="flex items-end gap-2">
          {/* ── Bouton "+" (popover upload) ── */}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              disabled={disabled}
              title="Joindre un document"
              className={`p-3 rounded-xl border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                menuOpen
                  ? "bg-surface-2 border-zinc-600 text-zinc-100"
                  : "bg-surface-2 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600"
              }`}
            >
              <Plus size={18} className={`transition-transform ${menuOpen ? "rotate-45" : ""}`} />
            </button>

            {/* Popover */}
            {menuOpen && (
              <div className="absolute bottom-full left-0 mb-2 w-56 rounded-xl border border-zinc-700 bg-surface-2 shadow-xl shadow-black/40 overflow-hidden z-20">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="w-full flex items-center gap-3 px-4 py-3 text-sm text-zinc-200 hover:bg-surface-1 transition-colors disabled:opacity-50"
                >
                  {uploading ? (
                    <Loader2 size={16} className="animate-spin text-primary-400" />
                  ) : (
                    <Upload size={16} className="text-zinc-400" />
                  )}
                  <span>{uploading ? "Upload en cours..." : "Uploader un PDF"}</span>
                </button>
                <div className="px-4 py-2 text-[11px] text-zinc-500 border-t border-zinc-700/60 flex items-center gap-1.5">
                  <FileText size={12} />
                  Le document sera indexé pour le RAG
                </div>
              </div>
            )}

            {/* Input file caché */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileSelect(file);
                e.target.value = "";
              }}
            />
          </div>

          {/* ── Textarea ── */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Pose ta question..."
              rows={1}
              className="w-full resize-none rounded-xl bg-surface-2 border border-zinc-700 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors"
              disabled={disabled}
            />
          </div>

          {/* ── Toggle Recherche web ── */}
          <button
            onClick={() => setWebSearch((v) => !v)}
            disabled={disabled}
            title={webSearch ? "Désactiver la recherche web" : "Activer la recherche web"}
            aria-pressed={webSearch}
            className={`p-3 rounded-xl border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              webSearch
                ? "bg-primary-600/20 border-primary-500 text-primary-400"
                : "bg-surface-2 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600"
            }`}
          >
            <Globe size={18} />
          </button>

          {/* ── Bouton Envoyer ── */}
          <button
            onClick={handleSend}
            disabled={!input.trim() || disabled}
            title="Envoyer"
            className="p-3 rounded-xl bg-primary-600 hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed text-zinc-950 transition-colors"
          >
            {disabled ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
          </button>
        </div>
      </div>
    </div>
  );
}
