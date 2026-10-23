/** @type {import('tailwindcss').Config} */

const token = (name) => `rgb(var(--color-${name}) / <alpha-value>)`;

module.exports = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: token("bg"),
        surface: {
          DEFAULT: token("surface"),
          raised: token("surface-raised"),
        },
        border: token("border"),
        grid: token("grid"),
        brand: {
          DEFAULT: token("brand-500"),
          400: token("brand-400"),
          500: token("brand-500"),
          600: token("brand-600"),
        },
        critical: token("critical"),
        high: token("high"),
        medium: token("medium"),
        low: token("low"),
        info: token("info"),
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      boxShadow: {
        panel: "0 1px 2px 0 rgb(0 0 0 / 0.35)",
        overlay: "0 16px 40px -12px rgb(0 0 0 / 0.6)",
        focus: "0 0 0 2px rgb(var(--color-brand-500) / 0.55)",
      },
      borderRadius: {
        card: "0.75rem",
      },
    },
  },
  plugins: [],
};
