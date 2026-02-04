/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}", "./pages/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#15AEC6",
        secondary: "#30D3C7",
        accent: "#0466BE"
      },
      fontFamily: {
        vazir: ['"Vazirmatn"', "sans-serif"]
      }
    }
  },
  plugins: []
};