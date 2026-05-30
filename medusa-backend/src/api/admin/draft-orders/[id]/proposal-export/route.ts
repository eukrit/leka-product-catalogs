import type { MedusaRequest, MedusaResponse } from "@medusajs/framework/http"
import { Modules } from "@medusajs/framework/utils"

/**
 * GET /admin/draft-orders/:id/proposal-export
 *
 * Pre-joins a Draft Order with the expansions the leka-projects
 * `proposal_engine` adapter needs, in a single HTTP call:
 *   - cart (items, region, currency, customer)
 *   - per-item variant + product (title, metadata, images)
 *
 * Why a custom endpoint instead of `?expand=...` on the standard route?
 * The proposal adapter's BoQ contract (plan §C3) is stable; pinning the
 * shape here means schema changes don't require a leka-projects redeploy.
 * Today we just return the standard Order DTO with all relations loaded —
 * if the contract drifts, we shape it here without changing the Python adapter.
 *
 * Auth: admin (JWT, or a secret admin API key issued in the Medusa admin UI).
 *
 * For the proposal_engine adapter we authenticate with the secret admin API
 * key via HTTP Basic — the key is the username and the password is empty:
 *   `Authorization: Basic base64("<api-key>:")`
 * Medusa's built-in admin route middleware accepts Basic auth for secret keys.
 * Note: `x-medusa-access-token` and `Authorization: Bearer <key>` both 401
 * (verified live 2026-05-29). The downstream Python adapter
 * (`eukrit/leka-projects:src/proposal_engine/medusa_adapter.py`, v1.52.0) uses
 * `requests(..., auth=(key, ""))`.
 * The key lives in GCP Secret Manager as `medusa-admin-api-key-proposal-engine`.
 */
export async function GET(req: MedusaRequest, res: MedusaResponse) {
  const { id } = req.params

  const orderModule = req.scope.resolve(Modules.ORDER)
  let order: any
  try {
    order = await (orderModule as any).retrieveOrder(id, {
      relations: [
        "items",
        "items.variant",
        "items.variant.product",
        "items.variant.product.images",
        "shipping_address",
        "billing_address",
        "shipping_methods",
      ],
    })
  } catch (err: any) {
    console.log(`[proposal-export] order ${id} not found: ${err?.message}`)
    return res.status(404).json({ message: `draft order ${id} not found` })
  }

  // The proposal_engine adapter reads draft_order.cart.items + draft_order.cart.region.
  // Medusa v2 stores items + region directly on the order; build the
  // legacy `cart`-shaped wrapper so the adapter works without v2/v1 quirks.
  const cart = {
    region: { currency_code: order.currency_code },
    region_id: order.region_id,
    currency_code: order.currency_code,
    email: order.email,
    customer_id: order.customer_id,
    items: (order.items || []).map((li: any) => ({
      id: li.id,
      title: li.title,
      quantity: li.quantity,
      unit_price: li.unit_price,
      compare_at_unit_price: li.compare_at_unit_price,
      metadata: li.metadata || {},
      variant: li.variant
        ? {
            id: li.variant.id,
            sku: li.variant.sku,
            title: li.variant.title,
            metadata: li.variant.metadata || {},
            product: li.variant.product
              ? {
                  id: li.variant.product.id,
                  title: li.variant.product.title,
                  metadata: li.variant.product.metadata || {},
                  images: (li.variant.product.images || []).map((img: any) => ({
                    id: img.id,
                    url: img.url,
                  })),
                }
              : null,
          }
        : null,
    })),
  }

  return res.json({
    id: order.id,
    display_id: order.display_id,
    status: order.status,
    metadata: order.metadata || {},
    shipping_address: order.shipping_address || null,
    billing_address: order.billing_address || null,
    cart,
    // Also include the raw items[] for adapters that read either shape.
    items: cart.items,
  })
}
