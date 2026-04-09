/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        mist: "#e2e8f0",
        ember: "#f97316",
        gold: "#facc15",
        pine: "#14532d",
        mint: "#bbf7d0",
        rose: "#ef4444",
        sand: "#f8fafc"
      },
      boxShadow: {
        panel: "0 18px 48px rgba(15, 23, 42, 0.12)"
      },
      fontFamily: {
        display: ["Georgia", "serif"],
        body: ["'Trebuchet MS'", "sans-serif"]
      }
    }
  },
  plugins: []
};
