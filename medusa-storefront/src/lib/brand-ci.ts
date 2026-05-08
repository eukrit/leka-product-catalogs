// Per-brand corporate identity (CI) registry — logos, favicons, palettes, fonts.
// Sourced from each vendor's public homepage on 2026-05-07. See BUILD_LOG / CHANGELOG.
// Keep entries small — one record per brand slug. Logos live under /public/brands/<slug>/.

export interface BrandPalette {
  primary: string
  secondary: string
  ink: string
  paper: string
}

export interface BrandFonts {
  // CSS variable name set by next/font (e.g. "--font-poppins").
  // Mapped to --brand-heading at the brand layout root so Tailwind's font-heading uses it.
  headingVar: string
  // Body stays Manrope across all brands for consistent readability.
}

export interface BrandCI {
  slug: string
  logo?: string         // /brands/<slug>/logo.{svg,png,jpg}; falls back to letter badge if undefined
  logoSquare?: string   // optional icon mark
  logoBg?: string       // optional fill for the logo wrapper (used when logo is white-on-transparent)
  favicon?: string      // /brands/<slug>/favicon.{png,ico}
  palette: BrandPalette
  fonts: BrandFonts
  tagline: string
}

export const BRAND_CI: Record<string, BrandCI> = {
  wisdom: {
    slug: "wisdom",
    logo: "/brands/wisdom/logo.png",
    favicon: "/brands/wisdom/favicon.png",
    palette: {
      primary: "#FCB822",
      secondary: "#1D3A8A",
      ink: "#0F1B3D",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-poppins" },
    tagline: "Commercial playground equipment built for durability and safety.",
  },
  vinci: {
    slug: "vinci",
    logo: "/brands/vinci/logo-white.png",
    logoBg: "#970260",
    favicon: "/brands/vinci/favicon.png",
    palette: {
      primary: "#970260",
      secondary: "#182557",
      ink: "#1A1A1A",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-montserrat" },
    tagline: "Playground equipment producer — Vinci Play.",
  },
  berliner: {
    slug: "berliner",
    logo: "/brands/berliner/logo.png",
    favicon: "/brands/berliner/favicon.png",
    palette: {
      primary: "#00827A",
      secondary: "#00534F",
      ink: "#0E1F1E",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-roboto" },
    tagline: "Rope play equipment — Berliner Seilfabrik.",
  },
  eurotramp: {
    slug: "eurotramp",
    logo: "/brands/eurotramp/logo.svg",
    favicon: "/brands/eurotramp/favicon.png",
    palette: {
      primary: "#0062AF",
      secondary: "#6B9950",
      ink: "#0E1B33",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-open-sans" },
    tagline:
      "Worldwide leading trampoline manufacturer with 50+ years of experience.",
  },
  rampline: {
    slug: "rampline",
    logo: "/brands/rampline/logo.svg",
    favicon: "/brands/rampline/favicon.png",
    palette: {
      primary: "#182557",
      secondary: "#970260",
      ink: "#0E1633",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-lato" },
    tagline:
      "Equipment for physical play, recreation and training challenging balance.",
  },
  "4soft": {
    slug: "4soft",
    // No logo asset on 4soft.cz public homepage (SPA). Falls back to letter badge.
    favicon: undefined,
    palette: {
      primary: "#FFA900",
      secondary: "#182557",
      ink: "#1A1A1A",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-nunito" },
    tagline: "EPDM playground surfaces & 3D elements.",
  },
  vortex: {
    slug: "vortex",
    logo: "/brands/vortex/logo.svg",
    logoSquare: "/brands/vortex/logo-square.png",
    logoBg: "#153CBA",
    favicon: "/brands/vortex/favicon.png",
    palette: {
      primary: "#153CBA",
      secondary: "#FFE000",
      ink: "#161A48",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-inter" },
    tagline:
      "Splashpad® and aquatic play solutions for municipal parks and commercial destinations.",
  },
  weplay: {
    slug: "weplay",
    logo: "/brands/weplay/logo.jpg",
    favicon: "/brands/weplay/favicon.ico",
    palette: {
      primary: "#0099CC",
      secondary: "#F9A825",
      ink: "#0E2A33",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-nunito" },
    tagline:
      "Sensory and educational play equipment helping children develop character and self-esteem.",
  },
}

export function getBrandCI(slug: string): BrandCI | undefined {
  return BRAND_CI[slug]
}
