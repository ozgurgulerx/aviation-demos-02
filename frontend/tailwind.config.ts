import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Aviation palette
        av: {
          navy: "hsl(var(--av-navy))",
          midnight: "hsl(var(--av-midnight))",
          sky: "hsl(var(--av-sky))",
          silver: "hsl(var(--av-silver))",
          gold: "hsl(var(--av-gold))",
          green: "hsl(var(--av-green))",
          red: "hsl(var(--av-red))",
          warm: "hsl(var(--av-warm))",
          surface: "hsl(var(--av-surface))",
          fabric: "hsl(var(--av-fabric))",
          azure: "hsl(var(--av-azure))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "av-glow-pulse": {
          "0%, 100%": { opacity: "0.4", transform: "scale(1)" },
          "50%": { opacity: "0.8", transform: "scale(1.05)" },
        },
        "av-particle": {
          "0%": { opacity: "0", transform: "translateY(0)" },
          "20%": { opacity: "1" },
          "100%": { opacity: "0", transform: "translateY(-20px)" },
        },
      },
      animation: {
        "av-glow-pulse": "av-glow-pulse 2s ease-in-out infinite",
        "av-particle": "av-particle 1.5s ease-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
