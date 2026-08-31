import type { Config } from "tailwindcss";

/* « Ciel nocturne » — palette sombre froide, accent bleu.
   surface / primary / zinc redéfinis en tons ardoise + bleu afin que
   l'ensemble de l'app (y compris les pages pas encore restylées) hérite du
   thème sans toucher au balisage. */
const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        /* Accent bleu — la clarté de la compréhension */
        primary: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
          950: "#172554",
        },
        /* Surfaces ardoise nuit, du fond vers l'élévation */
        surface: {
          0: "#0b0f16",
          1: "#111722",
          2: "#182030",
          3: "#1f2937",
          4: "#283345",
        },
        /* Zinc froid — gris ardoise pour texte/filets */
        zinc: {
          50: "#f8fafc",
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#94a3b8",
          500: "#64748b",
          600: "#475569",
          700: "#334155",
          800: "#1e293b",
          900: "#0f172a",
          950: "#020617",
        },
        /* Vert — maîtrise */
        sage: {
          DEFAULT: "#4ade80",
          soft: "rgba(74, 222, 128, 0.14)",
        },
      },
      fontFamily: {
        display: ["Fraunces", "Georgia", "serif"],
        sans: ["Manrope", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-in-out",
        "slide-up": "slideUp 0.3s ease-out",
        "pulse-soft": "pulseSoft 2s ease-in-out infinite",
        "bubble-in": "bubbleIn 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)",
        "bubble-user": "bubbleUser 0.35s cubic-bezier(0.34, 1.56, 0.64, 1)",
        "typing-dot": "typingDot 1.4s infinite ease-in-out",
        "glow-pulse": "glowPulse 3s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.7" },
        },
        bubbleIn: {
          "0%": { opacity: "0", transform: "scale(0.85) translateY(12px)" },
          "60%": { opacity: "1", transform: "scale(1.02) translateY(-2px)" },
          "100%": { opacity: "1", transform: "scale(1) translateY(0)" },
        },
        bubbleUser: {
          "0%": { opacity: "0", transform: "scale(0.85) translateX(12px)" },
          "60%": { opacity: "1", transform: "scale(1.02) translateX(-2px)" },
          "100%": { opacity: "1", transform: "scale(1) translateX(0)" },
        },
        typingDot: {
          "0%, 80%, 100%": { opacity: "0.3", transform: "scale(0.8)" },
          "40%": { opacity: "1", transform: "scale(1)" },
        },
        glowPulse: {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(59, 130, 246, 0)" },
          "50%": { boxShadow: "0 0 22px 2px rgba(59, 130, 246, 0.14)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
