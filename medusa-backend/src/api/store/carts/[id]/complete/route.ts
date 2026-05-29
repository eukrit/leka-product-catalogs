import type { MedusaRequest, MedusaResponse } from "@medusajs/framework/http"
import { Modules } from "@medusajs/framework/utils"
import { createOrderWorkflow } from "@medusajs/medusa/core-flows"

/**
 * POST /store/carts/:id/complete  (Leka catalogs override)
 *
 * Leka catalogs are a B2B "send to proposal" flow — there are no shipping
 * methods, no payment providers, and no inventory tracking. The stock
 * Medusa cart-complete workflow always fails here because it expects
 * shipping_methods + a payment_collection with an authorized session.
 *
 * The storefront (eukrit/leka-website/catalogs) calls
 * `sdk.store.cart.complete(cartId, ...)` which hits this path, and expects
 * either `{ type: "order", order }` (success) or an error message it can
 * surface. We give it the success shape by creating a *draft* order from
 * the cart and returning that — the proposal_engine operator then picks
 * the draft order up via the `proposal-created` subscriber.
 *
 * This intentionally bypasses `completeCartWorkflow` because the
 * shipping/payment requirements don't apply. Carts created or cached in
 * localStorage before the SGD region was added (v2.33.0) still work: the
 * createOrderWorkflow falls back to "any" region if `cart.region_id` is
 * stale, and uses `cart.currency_code` (or the region's) directly.
 *
 * Shape matches what `@medusajs/js-sdk`'s `store.cart.complete()` returns
 * so no storefront changes are needed.
 */
export async function POST(req: MedusaRequest, res: MedusaResponse) {
  const cartId = req.params.id as string
  if (!cartId) {
    return res.status(400).json({ message: "cart id is required" })
  }

  const cartModule = req.scope.resolve(Modules.CART)
  let cart: any
  try {
    cart = await (cartModule as any).retrieveCart(cartId, {
      relations: ["items", "shipping_address", "billing_address"],
    })
  } catch (err: any) {
    console.log(`[cart-complete] cart ${cartId} not found: ${err?.message}`)
    return res.status(404).json({ message: `cart ${cartId} not found` })
  }

  if (!cart.items || cart.items.length === 0) {
    return res.status(400).json({ message: "cart is empty" })
  }

  // The cart-complete SDK call typically PATCHes email + shipping_address
  // first, so by the time we get here the cart should carry both. We still
  // fall back to a sentinel email so createOrderWorkflow doesn't reject
  // the input — the proposal operator gets the real customer info from
  // shipping_address either way.
  const email = (typeof cart.email === "string" && cart.email)
    || "proposal-builder@catalogs.leka.studio"

  const items = cart.items.map((li: any) => ({
    variant_id: li.variant_id,
    quantity: Number(li.quantity) || 1,
    unit_price: Number(li.unit_price) || 0,
    // createOrderWorkflow's validateLineItemPricesStep wants `title: string`
    // and prepareLineItemData reads title/subtitle/thumbnail. Fall back to
    // the variant SKU-ish identifier we still have on the line item.
    title: (li.title && String(li.title).trim()) || li.product_title || li.variant_sku || "Item",
    subtitle: li.subtitle || undefined,
    thumbnail: li.thumbnail || undefined,
    metadata: {
      ...(li.metadata || {}),
      proposal_builder: true,
      source_cart_item_id: li.id,
    },
  }))

  const cartMeta = (cart.metadata && typeof cart.metadata === "object")
    ? (cart.metadata as Record<string, unknown>)
    : {}

  const orderInput: any = {
    region_id: cart.region_id || undefined,
    currency_code: cart.currency_code || undefined,
    email,
    customer_id: cart.customer_id || undefined,
    sales_channel_id: cart.sales_channel_id || undefined,
    status: "draft",
    items,
    metadata: {
      ...cartMeta,
      proposal_builder: true,
      source_cart_id: cartId,
      created_via: "storefront-complete",
      created_at: new Date().toISOString(),
    },
  }

  if (cart.shipping_address) {
    orderInput.shipping_address = { ...cart.shipping_address }
    delete orderInput.shipping_address.id
  }
  if (cart.billing_address) {
    orderInput.billing_address = { ...cart.billing_address }
    delete orderInput.billing_address.id
  }

  try {
    const { result: order } = await createOrderWorkflow(req.scope).run({
      input: orderInput,
    })

    // Storefront expects `{ type: "order", order: { id, display_id, ... } }`
    // — mirror Medusa's stock cart-complete response shape.
    return res.status(200).json({
      type: "order",
      order: {
        id: order.id,
        display_id: (order as any).display_id ?? null,
        status: order.status,
        currency_code: (order as any).currency_code,
        email: (order as any).email,
        metadata: (order as any).metadata ?? null,
      },
    })
  } catch (err: any) {
    console.log(
      `[cart-complete] createOrderWorkflow failed for cart ${cartId}: ${err?.message}\n${err?.stack || ""}`
    )
    return res.status(400).json({
      message: err?.message || "failed to create draft order",
      type: err?.type || "unknown_error",
    })
  }
}
