// Per-brand corporate identity (CI) registry — palettes, fonts, logo treatment.
//
// Palettes pulled directly from each vendor's production stylesheet (or
// homepage HTML when CSS-vars are inlined). Confidence + evidence per brand
// recorded inline so future audits can re-verify without re-running the
// scrape. Last verified 2026-05-08.
//
// Substitutions: vendors using Adobe Typekit / proprietary display faces
// (Berliner = myriad-pro, Vinci = VolteRounded, Rampline = motiva-sans,
// WePlay = CJK system stack) cannot be redistributed via next/font/google,
// so we pick the closest open-source alternative and keep the heading
// distinct from body where the vendor does. Documented per brand so a
// swap to a self-hosted file is a one-line change.

export interface BrandPalette {
  primary: string
  secondary: string
  accent?: string  // optional pop/CTA — Vortex hot-pink, Eurotramp red, etc.
  ink: string
  paper: string
}

export interface BrandFonts {
  // Heading next/font CSS variable. Mapped to --brand-heading at the brand
  // layout root so Tailwind's `font-heading` utility resolves correctly.
  headingVar: string
  // Body next/font CSS variable. Mapped to --brand-body at the brand layout
  // root. When omitted, body inherits the global Manrope.
  bodyVar?: string
}

export interface BrandCI {
  slug: string
  logo?: string         // /brands/<slug>/logo.{svg,png,jpg}; falls back to letter badge
  logoSquare?: string   // optional icon mark
  logoBg?: string       // wrapper fill — required when logo is white-on-transparent
  favicon?: string
  palette: BrandPalette
  fonts: BrandFonts
  tagline: string
}

export const BRAND_CI: Record<string, BrandCI> = {
  // Wisdom Playgrounds — verified in-browser at wisdomplaygroundsint.com on
  // 2026-05-08 via Chrome DevTools color histogram + computed styles:
  // rgb(31,74,131) = #1F4A83 navy (167 hits, dominant — header pill, hero
  // bg, footer); rgb(251,190,47) = #FBBE2F amber (52 hits — logo "i" dot,
  // "O" letter, accent buttons). Body font Roboto sitewide. Logo is a
  // navy "Wi" mark + WISDOM wordmark with the second "O" rendered amber;
  // the previous theme had primary/secondary swapped.
  wisdom: {
    slug: "wisdom",
    logo: "/brands/wisdom/logo.png",
    favicon: "/brands/wisdom/favicon.png",
    palette: {
      primary: "#1F4A83",     // verified — corporate navy
      secondary: "#FBBE2F",   // verified — accent amber
      ink: "#0F1B3D",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-roboto", bodyVar: "--font-roboto" },
    tagline: "Playground equipment built for durability and safety.",
  },

  // Vinci Play — verified from vinci-play.com/template/css/main.css:
  // #8A3492 purple (56 hits, dominant) + #FBBE2F yellow (16) + #E9592C
  // orange accent (8). Heading is custom VolteRounded-Bold; substitute
  // Montserrat for similar geometric weight. Body Open Sans matches.
  vinci: {
    slug: "vinci",
    logo: "/brands/vinci/logo-white.png",
    logoBg: "#8A3492",
    favicon: "/brands/vinci/favicon.png",
    palette: {
      primary: "#8A3492",     // verified — corporate purple
      secondary: "#FBBE2F",   // verified — secondary yellow
      accent: "#E9592C",      // verified — orange CTA
      ink: "#2B2B2B",         // verified
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-montserrat", bodyVar: "--font-open-sans" },
    tagline: "Playground equipment producer — Vinci Play.",
  },

  // Berliner Seilfabrik — verified from app.css + homepage HTML.
  // Primary is the dark teal #00534F (header/footer wordmark), with
  // #00827A as the lighter pair and #E6F3F2 as section cream. Typekit
  // serves myriad-pro; substitute Inter (closest open Myriad humanist).
  berliner: {
    slug: "berliner",
    logo: "/brands/berliner/logo.png",
    favicon: "/brands/berliner/favicon.png",
    palette: {
      primary: "#00534F",     // verified — dark teal (was secondary, swapped)
      secondary: "#00827A",   // verified — lighter teal
      accent: "#E6F3F2",      // verified — section cream tint
      ink: "#0E1F1E",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-inter", bodyVar: "--font-inter" },
    tagline: "Rope play equipment — Berliner Seilfabrik.",
  },

  // Eurotramp — verified from style_0933.min.css:
  // #0062AF corporate blue (92 hits) + #63727F slate (62) + #C80000 red
  // accent (9). Mask-icon color also #0062AF. Roboto Condensed sitewide.
  eurotramp: {
    slug: "eurotramp",
    logo: "/brands/eurotramp/logo.svg",
    favicon: "/brands/eurotramp/favicon.png",
    palette: {
      primary: "#0062AF",     // verified — corporate blue
      secondary: "#63727F",   // verified — slate (was wrong green #6B9950)
      accent: "#C80000",      // verified — red emphasis
      ink: "#010101",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-roboto-condensed", bodyVar: "--font-roboto-condensed" },
    tagline: "Worldwide leading trampoline manufacturer with 50+ years of experience.",
  },

  // Rampline — verified from rampline.com/wp-content/themes/rampline/style.css.
  // Distinctive lime + forest palette: #B5BC00 (button base, 8) + #2D5346
  // forest (12) on cream paper #F2F2EE (24). Typekit serves motiva-sans;
  // substitute Inter. Previous theme (navy + magenta) was completely wrong.
  rampline: {
    slug: "rampline",
    logo: "/brands/rampline/logo.svg",
    favicon: "/brands/rampline/favicon.png",
    palette: {
      primary: "#B5BC00",     // verified — lime CTA
      secondary: "#2D5346",   // verified — dark forest
      accent: "#CED600",      // verified — lime hover
      ink: "#313131",
      paper: "#F2F2EE",       // verified — warm off-white
    },
    fonts: { headingVar: "--font-inter", bodyVar: "--font-inter" },
    tagline:
      "Equipment for physical play, recreation and training challenging balance.",
  },

  // 4soft — verified from app-frontend.css:
  // #0089CF corporate blue (85 hits) + #CF0026 red (32) + #F99D1C orange
  // accent (20). Heading Nunito + body Lato loaded from Google Fonts on
  // their site. Previous theme had primary as orange — actually blue.
  "4soft": {
    slug: "4soft",
    favicon: undefined,        // SPA — header/favicon rendered client-side
    palette: {
      primary: "#0089CF",     // verified — corporate blue (was wrong #FFA900)
      secondary: "#CF0026",   // verified — corporate red
      accent: "#F99D1C",      // verified — orange
      ink: "#212529",
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-nunito", bodyVar: "--font-lato" },
    tagline: "EPDM playground surfaces & 3D elements.",
  },

  // Vortex Aquatic Structures — verified from main_4d2020b1.css:
  // #153CBA blue (132 hits, .--primary border) + #FF33D4 signature
  // hot-pink secondary (95) + #FFE000 yellow accent (11). Splashpad® is a
  // registered trademark. Heading Work Sans + body Nunito on their site.
  vortex: {
    slug: "vortex",
    logo: "/brands/vortex/logo.svg",
    logoSquare: "/brands/vortex/logo-square.png",
    logoBg: "#153CBA",
    favicon: "/brands/vortex/favicon.png",
    palette: {
      primary: "#153CBA",     // verified — corporate blue
      secondary: "#FF33D4",   // verified — signature hot-pink (was wrong #FFE000)
      accent: "#FFE000",      // verified — yellow accent (demoted from secondary)
      ink: "#000732",         // verified
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-work-sans", bodyVar: "--font-nunito" },
    tagline:
      "Splashpad® and aquatic play solutions for municipal parks and commercial destinations.",
  },

  // WePlay — verified in Chrome at weplay.com.tw on 2026-05-09 via computed-
  // style histogram across 3,000 elements:
  //   rgb(199,22,30)  = #C7161E red    (126 hits — dominant brand: nav links,
  //                                     CTA buttons, hero accent script)
  //   rgb(240,131,30) = #F0831E orange (34 hits — secondary, hero "We play"
  //                                     gradient, accent outlines)
  //   rgb(254,213,43) = #FED52B yellow (5 hits  — pop accent, cookie banner)
  // Body font is the Bootstrap system stack (Roboto fallback) — for the
  // storefront we substitute Nunito to match the playful rounded feel
  // without locking to a system face. Tagline pulled from the homepage hero.
  weplay: {
    slug: "weplay",
    logo: "/brands/weplay/logo.jpg",
    favicon: "/brands/weplay/favicon.ico",
    palette: {
      primary: "#C7161E",     // verified — corporate red
      secondary: "#F0831E",   // verified — corporate orange
      accent: "#FED52B",      // verified — yellow pop
      ink: "#212529",         // verified — Bootstrap-default body ink
      paper: "#FFFFFF",
    },
    fonts: { headingVar: "--font-nunito", bodyVar: "--font-nunito" },
    tagline: "We play, we learn — for the future.",
  },
}

export function getBrandCI(slug: string): BrandCI | undefined {
  return BRAND_CI[slug]
}
