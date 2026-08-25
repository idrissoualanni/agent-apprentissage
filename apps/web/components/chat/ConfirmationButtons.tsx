"use client";

interface ConfirmationButtonsProps {
  prompt: string;
  type: string;
  onConfirm: () => void;
  onCancel: () => void;
}

const TYPE_CONFIG: Record<string, { icon: string; color: string; glow: string }> = {
  quiz: { icon: "Q", color: "text-emerald-400", glow: "shadow-emerald-500/20" },
  feynman: { icon: "F", color: "text-amber-400", glow: "shadow-amber-500/20" },
  artifact: { icon: "A", color: "text-pink-400", glow: "shadow-pink-500/20" },
};

export function ConfirmationButtons({
  prompt,
  type,
  onConfirm,
  onCancel,
}: ConfirmationButtonsProps) {
  const config = TYPE_CONFIG[type] || { icon: "?", color: "text-primary-400", glow: "shadow-primary-500/20" };

  return (
    <div className="flex justify-start animate-bubble-in">
      <div className={`max-w-[80%] rounded-2xl p-4 border border-primary-500/30 bg-primary-500/10 shadow-lg ${config.glow} relative overflow-hidden`}>
        <div className="absolute inset-0 animate-glow-pulse pointer-events-none" />

        <div className="flex items-start gap-3 relative z-10">
          <div className={`w-9 h-9 rounded-full bg-primary-500/20 flex items-center justify-center ${config.color} font-bold text-sm flex-shrink-0 border border-primary-500/30`}>
            {config.icon}
          </div>
          <div className="flex-1">
            <p className="text-sm text-zinc-200 leading-relaxed">{prompt}</p>
            <div className="flex gap-2 mt-3">
              <button
                onClick={onConfirm}
                className="px-4 py-2 bg-primary-600 hover:bg-primary-500 text-white text-sm font-medium rounded-lg transition-all duration-200 hover:scale-105 hover:shadow-lg hover:shadow-primary-600/30 active:scale-95"
              >
                Oui, c'est parti
              </button>
              <button
                onClick={onCancel}
                className="px-4 py-2 bg-surface-3 hover:bg-zinc-600 text-zinc-300 text-sm font-medium rounded-lg transition-all duration-200 hover:scale-105 active:scale-95"
              >
                Pas maintenant
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
