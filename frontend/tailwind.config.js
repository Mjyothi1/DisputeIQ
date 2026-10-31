/** Colours are CSS-variable channels (see src/index.css) so light/dark share one set of class names. */
const c = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: c("background"),
        surface: c("surface"),
        foreground: c("foreground"),
        muted: { DEFAULT: c("muted"), foreground: c("muted-foreground") },
        border: c("border"),
        ring: c("ring"),
        primary: { DEFAULT: c("primary"), foreground: c("primary-foreground") },
        accent: { DEFAULT: c("accent"), foreground: c("foreground") },
        pass: c("pass"),
        fail: c("fail"),
        warn: c("warn"),
        info: c("info"),
      },
      fontFamily: {
        sans: ['"Public Sans Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ['"Source Serif 4 Variable"', "Georgia", "ui-serif", "serif"],
      },
      borderRadius: { control: "6px", panel: "10px" },
    },
  },
  plugins: [],
};
