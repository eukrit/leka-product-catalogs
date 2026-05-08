export interface VendorTheme {
  slug: string
  tagline: string
  origin: string
  colors: {
    primary: string
    accent: string
    accentContrast: string
    bg: string
    headerBg: string
    headerText: string
    headerBorder: string
  }
  hero: {
    bg: string
    textColor: string
    accentColor: string
  }
}

export const VENDOR_THEMES: Record<string, VendorTheme> = {
  berliner: {
    slug: "berliner",
    tagline: "Rope Play Since 1865",
    origin: "Made in Germany",
    colors: {
      primary: "#1C2B4B",
      accent: "#F04900",
      accentContrast: "#FFFFFF",
      bg: "#F8F7F4",
      headerBg: "#1C2B4B",
      headerText: "#FFFFFF",
      headerBorder: "#F04900",
    },
    hero: {
      bg: "linear-gradient(135deg, #1C2B4B 0%, #2E3F6B 100%)",
      textColor: "#FFFFFF",
      accentColor: "#F04900",
    },
  },
  eurotramp: {
    slug: "eurotramp",
    tagline: "Premium Trampolines",
    origin: "Made in Germany",
    colors: {
      primary: "#1A1A1A",
      accent: "#E30613",
      accentContrast: "#FFFFFF",
      bg: "#FFFFFF",
      headerBg: "#FFFFFF",
      headerText: "#1A1A1A",
      headerBorder: "#E30613",
    },
    hero: {
      bg: "linear-gradient(135deg, #E30613 0%, #B50010 100%)",
      textColor: "#FFFFFF",
      accentColor: "#FFFFFF",
    },
  },
  rampline: {
    slug: "rampline",
    tagline: "Motor Skill Playgrounds",
    origin: "Made in Norway",
    colors: {
      primary: "#0A0A0A",
      accent: "#C8FF00",
      accentContrast: "#0A0A0A",
      bg: "#FAFAF8",
      headerBg: "#0A0A0A",
      headerText: "#FFFFFF",
      headerBorder: "#C8FF00",
    },
    hero: {
      bg: "linear-gradient(135deg, #0A0A0A 0%, #1E1E1E 100%)",
      textColor: "#FFFFFF",
      accentColor: "#C8FF00",
    },
  },
  vortex: {
    slug: "vortex",
    tagline: "Aquatic Play, Splashpads & Waterslides",
    origin: "Made in Canada",
    colors: {
      primary: "#000732",
      accent: "#00B7E4",
      accentContrast: "#FFFFFF",
      bg: "#FFFFFF",
      headerBg: "#FFFFFF",
      headerText: "#000732",
      headerBorder: "#00B7E4",
    },
    hero: {
      bg: "linear-gradient(135deg, #153cba 0%, #000732 100%)",
      textColor: "#FFFFFF",
      accentColor: "#00B7E4",
    },
  },
  "4soft": {
    slug: "4soft",
    tagline: "EPDM Play Surfaces & 3D Elements",
    origin: "Made in Czech Republic",
    colors: {
      primary: "#1A1A1A",
      accent: "#FF6B00",
      accentContrast: "#FFFFFF",
      bg: "#FFFFFF",
      headerBg: "#FFFFFF",
      headerText: "#1A1A1A",
      headerBorder: "#FF6B00",
    },
    hero: {
      bg: "linear-gradient(135deg, #FF6B00 0%, #FF8C00 50%, #0095D9 100%)",
      textColor: "#FFFFFF",
      accentColor: "#FFFFFF",
    },
  },
}

export function getVendorTheme(slug: string): VendorTheme | undefined {
  return VENDOR_THEMES[slug]
}
