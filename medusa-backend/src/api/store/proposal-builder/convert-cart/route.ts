import type { MedusaRequest, MedusaResponse } from "@medusajs/framework/http"
import { Modules } from "@medusajs/framework/utils"
import { createOrderWorkflow } from "@medusajs/medusa/core-flows"

/**
 * POST /store/proposal-builder/convert-cart
 *
 * Sales-team "Send to Proposal" flow (Phase 2 of the proposal_engine).
 *
 * Body:
 *   {
 *     cart_id: string,                  // required — current storefront cart
 *     project_id?: string,              // e.g. "dulwich-singapore"; stored on the
 *                                       // draft order's metadata so the operator
 *                                       // can match it to a config.yaml
 *     project_name?: string,            // free text
 *     site_location?: string,
 *     project_details?: string,
 *     metadata?: Record<string, unknown>,// any extra payload for the proposal engine
 *   }
 *
 * What happens:
 *   1. Retrieve the cart with its line items + region.
 *   2. Build a `createOrderWorkflow` input with status="draft", copying each
 *      line item (variant_id, quantity, unit_price, title, metadata) and stamping
 *      `metadata.proposal_builder: true` on the order + every line item.
 *   3. Run the workflow → creates the draft order.
 *   4. Return { draft_order_id, display_id } so the storefront can show it.
 *
 * The originating cart is left alone — the storefront clears its localStorage
 * cart-id on success so the customer starts fresh. Cart is kept on the
 * server so a follow-up render can re-examine it if needed.
 *
 * Auth: store-side (publishable API key + optional customer session). No
 * admin token required — sales triggers this from the live storefront.
 *
 * The `draft-order.created` subscriber (src/subscribers/proposal-created.ts)
 * filters on `metadata.proposal_builder === true` and posts a Slack alert
 * to #leka-medusa-proposal so the proposal_engine operator knows to
 * grab the draft_order_id.
 */
export async function POST(req: MedusaRequest, res: MedusaResponse) {
  const body = (req.body as Record<string, unknown>) || {}
  const cartId = typeof body.cart_id === "string" ? body.cart_id : ""
  if (!cartId) {
    return res.status(400).json({ message: "cart_id is required" })
  }

  const projectId = typeof body.project_id === "string" ? body.project_id : null
  const projectName = typeof body.project_name === "string" ? body.project_name : null
  const siteLocation = typeof body.site_location === "string" ? body.site_location : null
  const projectDetails = typeof body.project_details === "string" ? body.project_details : null
  const extraMetadata = (body.metadata && typeof body.metadata === "object")
    ? (body.metadata as Record<string, unknown>)
    : {}

  // ── Retrieve the cart with line items + region ──
  const cartModule = req.scope.resolve(Modules.CART)
  let cart: any
  try {
    cart = await (cartModule as any).retrieveCart(cartId, {
      relations: ["items", "shipping_address", "billing_address"],
    })
  } catch (err: any) {
    console.log(`[proposal-builder] cart ${cartId} not found: ${err?.message}`)
    return res.status(404).json({ message: `cart ${cartId} not found` })
  }

  if (!cart.items || cart.items.length === 0) {
    return res.status(400).json({ message: "cart is empty — add items before sending to proposal" })
  }

  // ── Build the draft order input ──
  // Every line item gets metadata.proposal_builder=true + a few sensible
  // defaults (zone/category) so the proposal_engine adapter has something
  // to group by even before sales retags the lines in admin.
  const items = cart.items.map((li: any) => ({
    variant_id: li.variant_id,
    quantity: li.quantity,
    unit_price: li.unit_price,
    title: li.title || undefined,
    metadata: {
      ...(li.metadata || {}),
      proposal_builder: true,
      source_cart_item_id: li.id,
    },
  }))

  const orderInput: any = {
    region_id: cart.region_id,
    currency_code: cart.currency_code,
    email: cart.email || "proposal-builder@catalogs.leka.studio",
    customer_id: cart.customer_id || undefined,
    sales_channel_id: cart.sales_channel_id || undefined,
    status: "draft",
    items,
    metadata: {
      ...extraMetadata,
      proposal_builder: true,
      source_cart_id: cartId,
      project_id: projectId,
      project_name: projectName,
      site_location: siteLocation,
      project_details: projectDetails,
      created_via: "send-to-proposal",
      created_at: new Date().toISOString(),
    },
  }

  // Copy shipping/billing address if present — operator may need them in
  // the rendered proposal even though no fulfillment happens here.
  if (cart.shipping_address) {
    orderInput.shipping_address = { ...cart.shipping_address }
    delete orderInput.shipping_address.id
  }
  if (cart.billing_address) {
    orderInput.billing_address = { ...cart.billing_address }
    delete orderInput.billing_address.id
  }

  // ── Run the workflow ──
  try {
    const { result: order } = await createOrderWorkflow(req.scope).run({
      input: orderInput,
    })
    return res.status(201).json({
      draft_order_id: order.id,
      display_id: (order as any).display_id ?? null,
      status: order.status,
      proposal_builder: true,
      message: "Draft order created — paste the draft_order_id into projects/<id>/config.yaml boq.sources",
    })
  } catch (err: any) {
    console.log(`[proposal-builder] createOrderWorkflow failed for cart ${cartId}: ${err?.message}`)
    return res.status(500).json({
      message: "failed to create draft order",
      detail: err?.message || String(err),
    })
  }
}
