import type { Config } from "tailwindcss"

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        leka: {
          purple: "#8003FF",
          navy: "#182557",
          cream: "#FFF9E6",
          magenta: "#970260",
          amber: "#FFA900",
          "red-orange": "#E54822",
        },
      },
      fontFamily: {
        sans: ["Manrope", "system-ui", "sans-serif"],
      },
      borderRadius: {
        card: "16px",
        button: "8px",
        badge: "9999px",
      },
      boxShadow: {
        card: "0px 2px 8px rgba(24, 37, 87, 0.08)",
        "card-hover": "0px 4px 16px rgba(24, 37, 87, 0.12)",
      },
    },
  },
  plugins: [],
}

export default config
