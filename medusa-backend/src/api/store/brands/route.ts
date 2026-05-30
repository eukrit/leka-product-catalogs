import type { MedusaRequest, MedusaResponse } from "@medusajs/framework/http"
import { BRAND_MODULE } from "../../../modules/brand"

/**
 * GET /store/brands
 *
 * Lists all brands for the storefront brand-switcher. Replaces the old
 * "one sales channel per brand" topology — brands are now a queryable
 * first-class entity linked to products, while the cart lives in a single
 * shared "Leka Catalogs" sales channel and can carry products from any
 * combination of brands.
 *
 * Query params:
 *   handle  (optional) — filter to a single brand by handle
 *   limit   (optional, default 50)
 *   offset  (optional, default 0)
 *
 * Auth: store-side (publishable API key required, no customer session).
 */
export async function GET(req: MedusaRequest, res: MedusaResponse) {
  const brandService: any = req.scope.resolve(BRAND_MODULE)

  const handleFilter = typeof req.query.handle === "string" ? req.query.handle : undefined
  const limit = Math.min(parseInt(String(req.query.limit ?? "50"), 10) || 50, 200)
  const offset = parseInt(String(req.query.offset ?? "0"), 10) || 0

  const filters: Record<string, unknown> = {}
  if (handleFilter) filters.handle = handleFilter

  const [brands, count] = await brandService.listAndCountBrands(filters, {
    skip: offset,
    take: limit,
    order: { name: "ASC" },
  })

  res.json({
    brands: brands.map((b: any) => ({
      id: b.id,
      name: b.name,
      handle: b.handle,
      description: b.description ?? null,
      logo_url: b.logo_url ?? null,
    })),
    count,
    offset,
    limit,
  })
}
