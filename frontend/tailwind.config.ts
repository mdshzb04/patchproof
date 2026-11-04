import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        graphite: "#101318",
        rail: "#14181f",
        panel: "#1b212b",
        inset: "#12161c",
        line: "#2e3644",
        ink: "#e6edf7",
        mute: "#8b95a7",
        signal: "#3c7dff",
        crit: "#e15d4f",
        high: "#e39b4b",
        med: "#d4b25c",
        low: "#7ea2d6",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      borderRadius: {
        sm: "2px",
      },
    },
  },
  plugins: [],
};

export default config;
