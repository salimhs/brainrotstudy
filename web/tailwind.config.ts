import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "hsl(240 10% 4%)",
        panel: "hsl(240 8% 8%)",
        border: "hsl(240 6% 16%)",
        muted: "hsl(240 4% 64%)",
        accent: "hsl(292 91% 60%)",
        accent2: "hsl(196 94% 58%)",
        success: "hsl(142 71% 45%)",
        danger: "hsl(0 72% 51%)",
      },
      boxShadow: {
        glow: "0 0 40px 8px rgba(214, 88, 255, 0.25)",
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Inter", "sans-serif"],
      },
      keyframes: {
        shimmer: {
          "0%, 100%": { transform: "translateX(-100%)" },
          "50%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        shimmer: "shimmer 2.2s linear infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
