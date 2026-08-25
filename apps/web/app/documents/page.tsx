"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { documents } from "@/lib/api";
import type { Document as Doc, IndexingStatus } from "@/lib/types";
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  User,
  Cpu,
  Upload,
  Trash2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/profile", label: "Profil", icon: User },
  { href: "/models", label: "Modeles", icon: Cpu },
];

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [status, setStatus] = useState<IndexingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [docsData, statusData] = await Promise.all([
        documents.list(),
        documents.status().catch(() => null),
      ]);
      setDocs(docsData);
      setStatus(statusData);
    } catch (err) {
      console.error("Failed to load documents:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      await documents.upload(file);
      await loadData();
    } catch (err) {
      console.error("Upload failed:", err);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleDelete = async (filename: string) => {
    try {
      await documents.delete(filename);
      setDocs((prev) => prev.filter((d) => d.filename !== filename));
    } catch (err) {
      console.error("Delete failed:", err);
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
            const isActive = item.href === "/documents";
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
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Documents</h1>
          <label
            className={`flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg cursor-pointer transition-colors ${
              uploading ? "opacity-50 pointer-events-none" : ""
            }`}
          >
            <Upload size={16} />
            {uploading ? "Upload..." : "Uploader un PDF"}
            <input
              type="file"
              accept=".pdf"
              onChange={handleUpload}
              className="hidden"
            />
          </label>
        </div>

        {/* Indexing status */}
        {status && (
          <div className="mb-6 p-4 rounded-xl border border-zinc-800 bg-surface-1">
            <div className="flex items-center gap-2 text-sm text-zinc-400 mb-2">
              <CheckCircle2 size={16} className="text-emerald-400" />
              {status.indexed}/{status.total} document(s) indexe(s)
            </div>
            {status.pending.length > 0 && (
              <div className="flex items-center gap-2 text-sm text-yellow-400">
                <AlertCircle size={16} />
                {status.pending.length} en attente d'indexation
              </div>
            )}
          </div>
        )}

        {/* Documents list */}
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 rounded-xl bg-surface-1 animate-pulse" />
            ))}
          </div>
        ) : docs.length === 0 ? (
          <div className="text-center py-12 text-zinc-500">
            <FileText size={48} className="mx-auto mb-4 opacity-30" />
            <p className="text-lg font-medium">Aucun document</p>
            <p className="text-sm mt-1">Uploade un PDF pour commencer</p>
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between p-4 rounded-xl border border-zinc-800 bg-surface-1 hover:bg-surface-2 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <FileText size={20} className="text-zinc-400" />
                  <div>
                    <p className="text-sm font-medium text-zinc-200">{doc.filename}</p>
                    <p className="text-xs text-zinc-500">
                      {doc.num_chunks} chunk{doc.num_chunks > 1 ? "s" : ""}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(doc.filename)}
                  className="p-2 rounded-lg hover:bg-red-500/15 text-zinc-500 hover:text-red-400 transition-colors"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
