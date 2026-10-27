/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm graphite replaces Tailwind's default "slate".
        slate: {
          50: "#f6f5f3",
          100: "#e9e7e2",
          200: "#d8d4cb",
          300: "#b7b1a4",
          400: "#8f887a",
          500: "#6d665b",
          600: "#524d45",
          700: "#3a352f",
          800: "#282521",
          900: "#1c1a17",
          950: "#121110",
        },
        // Brand / primary-action teal.
        blue: {
          300: "#5eead4",
          400: "#2dd4bf",
          500: "#14b8a6",
          600: "#0d9488",
          700: "#0f766e",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      // Named small type scale for labels and badges.
      fontSize: {
        micro: ["10px", { lineHeight: "14px", letterSpacing: "0.05em" }],
        label: ["11px", { lineHeight: "16px", letterSpacing: "0.04em" }],
      },
      keyframes: {
        "alert-flash": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(239,68,68,0)" },
          "50%": { boxShadow: "0 0 0 6px rgba(239,68,68,0.25)" },
        },
      },
      animation: {
        "alert-flash": "alert-flash 1.1s ease-in-out 3",
      },
    },
  },
  plugins: [],
};
