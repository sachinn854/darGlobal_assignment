/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B1114",
        panel: "#111A1F",
        brass: "#C9A45E",
        paper: "#F4EFE6",
      },
      fontFamily: {
        display: ["Bodoni Moda", "Georgia", "serif"],
        sans: ["Manrope", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
