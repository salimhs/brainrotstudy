/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "hsl(222, 47%, 11%)",
        foreground: "hsl(210, 40%, 98%)",
        card: {
          DEFAULT: "hsl(222, 47%, 15%)",
          foreground: "hsl(210, 40%, 98%)",
        },
        primary: {
          DEFAULT: "hsl(262, 83%, 58%)",
          foreground: "hsl(210, 40%, 98%)",
        },
        secondary: {
          DEFAULT: "hsl(217, 33%, 17%)",
          foreground: "hsl(210, 40%, 98%)",
        },
        muted: {
          DEFAULT: "hsl(217, 33%, 17%)",
          foreground: "hsl(215, 20%, 65%)",
        },
        accent: {
          DEFAULT: "hsl(262, 83%, 58%)",
          foreground: "hsl(210, 40%, 98%)",
        },
        destructive: {
          DEFAULT: "hsl(0, 62%, 50%)",
          foreground: "hsl(210, 40%, 98%)",
        },
        border: "hsl(217, 33%, 25%)",
        input: "hsl(217, 33%, 17%)",
        ring: "hsl(262, 83%, 58%)",
      },
      borderRadius: {
        lg: "12px",
        md: "8px",
        sm: "4px",
      },
      keyframes: {
        "pulse-glow": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
      },
      animation: {
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
