import type { Config } from "tailwindcss";

/* « La lampe du tuteur » — palette sombre chaude.
   surface / primary / zinc sont redéfinies en tons espresso + ambre afin que
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
        /* Accent ambre — la lumière de la compréhension */
        primary: {
          50: "#fdf6e9",
          100: "#faead0",
          200: "#f5d5a0",
          300: "#efbc6e",
          400: "#f0b454",
          500: "#e8a33d",
          600: "#c98224",
          700: "#a8691b",
          800: "#8a5618",
          900: "#6b4213",
          950: "#40260a",
        },
        /* Surfaces espresso, du fond vers l'élévation */
        surface: {
          0: "#0f0d0a",
          1: "#161310",
          2: "#1e1a15",
          3: "#28221b",
          4: "#332c22",
        },
        /* Zinc chaud — remplace le gris froid de Tailwind pour texte/filets */
        zinc: {
          50: "#faf7f0",
          100: "#f2ecdf",
          200: "#e4dbc8",
          300: "#cfc3ab",
          400: "#b3a894",
          500: "#8b8069",
          600: "#6f6653",
          700: "#4a4335",
          800: "#322c22",
          900: "#211c14",
          950: "#171310",
        },
        /* Vert sauge — maîtrise */
        sage: {
          DEFAULT: "#8fb573",
          soft: "rgba(143, 181, 115, 0.14)",
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
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(232, 163, 61, 0)" },
          "50%": { boxShadow: "0 0 22px 2px rgba(232, 163, 61, 0.12)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
