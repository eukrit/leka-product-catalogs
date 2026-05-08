// Score product images so photos rank above drawings, CAD, and certificates.
// Vendors deliver images in inconsistent order; we use filename hints to pick
// the most marketable image for cards and gallery defaults.

const PENALTY_PATTERNS: Array<[RegExp, number]> = [
  [/\b(certificate|cert|tuv|iso|ce[-_]?mark|compliance)\b/i, -100],
  [/\b(drawing|dwg|cad|blueprint|wireframe|line[-_]?art)\b/i, -80],
  [/\b(spec|specification|tech(nical)?|datasheet|data[-_]?sheet)\b/i, -60],
  [/\b(dim|dimension|measure|measurement|footprint|footing|installation)\b/i, -50],
  [/\b(plan|elevation|side[-_]?view|top[-_]?view|front[-_]?view|section)\b/i, -40],
  [/\b(sketch|schematic|diagram)\b/i, -40],
  [/\.(svg|dwg|dxf|pdf)(\?|$)/i, -30],
]

const REWARD_PATTERNS: Array<[RegExp, number]> = [
  [/\b(hero|main|primary|cover|featured)\b/i, 30],
  [/\b(photo|render|lifestyle|in[-_]?use|context)\b/i, 20],
  [/\b(product|catalog|catalogue)\b/i, 5],
  [/-1\.(jpe?g|png|webp)(\?|$)/i, 10],
  [/\.(jpe?g|webp|png)(\?|$)/i, 5],
]

export function scoreImage(url: string | null | undefined): number {
  if (!url) return -Infinity
  let score = 0
  for (const [re, delta] of PENALTY_PATTERNS) if (re.test(url)) score += delta
  for (const [re, delta] of REWARD_PATTERNS) if (re.test(url)) score += delta
  return score
}

export interface ScorableImage {
  url: string
}

export function pickPrimaryImage(
  thumbnail: string | null | undefined,
  images: ReadonlyArray<ScorableImage> | null | undefined
): string | null {
  const candidates: string[] = []
  if (thumbnail) candidates.push(thumbnail)
  if (images) for (const img of images) if (img?.url) candidates.push(img.url)
  if (candidates.length === 0) return null

  let best = candidates[0]
  let bestScore = scoreImage(best)
  for (let i = 1; i < candidates.length; i++) {
    const s = scoreImage(candidates[i])
    if (s > bestScore) {
      bestScore = s
      best = candidates[i]
    }
  }
  if (thumbnail && scoreImage(thumbnail) === bestScore) return thumbnail
  return best
}

export function sortImagesByScore<T extends ScorableImage>(
  images: ReadonlyArray<T> | null | undefined
): T[] {
  if (!images) return []
  return [...images].sort((a, b) => scoreImage(b?.url) - scoreImage(a?.url))
}
