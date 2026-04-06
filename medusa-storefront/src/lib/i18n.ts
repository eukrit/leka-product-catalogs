/**
 * Locale management for multi-language support.
 * Uses Medusa v2 Translation Module (v2.12.3+).
 * Stores locale preference in localStorage.
 */

export const LOCALES = [
  { code: "en", label: "English", flag: "🇬🇧" },
  { code: "th", label: "ไทย", flag: "🇹🇭" },
  { code: "zh", label: "中文", flag: "🇨🇳" },
] as const

export type Locale = (typeof LOCALES)[number]["code"]

const STORAGE_KEY = "leka_locale"

export function getLocale(): Locale {
  if (typeof window === "undefined") return "en"
  return (localStorage.getItem(STORAGE_KEY) as Locale) || "en"
}

export function setLocale(locale: Locale) {
  localStorage.setItem(STORAGE_KEY, locale)
}

/**
 * Get translated field from product metadata.
 * Falls back to base field if translation not available.
 */
export function getTranslatedField(
  product: { description?: string; metadata?: Record<string, unknown> },
  field: string,
  locale: Locale
): string {
  if (locale === "en") return (product as any)[field] || ""

  const metaKey = locale === "th" ? `${field}_th` : `${field}_cn`
  const translated = product.metadata?.[metaKey] as string | undefined
  return translated || (product as any)[field] || ""
}
