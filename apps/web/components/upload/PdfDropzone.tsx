"use client";

import { useState, useCallback } from "react";
import type { FileRejection } from "react-dropzone";
import { Upload, FileText, X } from "lucide-react";

interface PdfDropzoneProps {
  onUpload: (file: File) => Promise<void>;
}

export function PdfDropzone({ onUpload }: PdfDropzoneProps) {
  const [isDragActive, setIsDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      if (file.type !== "application/pdf") {
        setError("Seuls les fichiers PDF sont accepts.");
        return;
      }
      setError(null);
      setUploading(true);
      try {
        await onUpload(file);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erreur d'upload");
      } finally {
        setUploading(false);
      }
    },
    [onUpload]
  );

  return (
    <div
      className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
        isDragActive
          ? "border-primary-500 bg-primary-500/5"
          : "border-zinc-700 hover:border-zinc-600"
      } ${uploading ? "opacity-50 pointer-events-none" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragActive(true);
      }}
      onDragLeave={() => setIsDragActive(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragActive(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
    >
      <input
        type="file"
        accept=".pdf"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = "";
        }}
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
      />
      <FileText size={36} className="mx-auto mb-3 text-zinc-500" />
      <p className="text-sm text-zinc-300">
        {uploading ? "Upload en cours..." : "Glisse un PDF ici ou clique pour selectionner"}
      </p>
      {error && (
        <div className="mt-3 flex items-center justify-center gap-2 text-sm text-red-400">
          <X size={14} />
          {error}
        </div>
      )}
    </div>
  );
}
