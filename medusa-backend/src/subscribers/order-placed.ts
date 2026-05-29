import type { SubscriberArgs, SubscriberConfig } from "@medusajs/framework"
import { Modules } from "@medusajs/framework/utils"

/**
 * On order.placed:
 *   1. Post a summary to Slack #leka-medusa-order (team alert).
 *   2. Email an order confirmation to the customer, bcc the team inbox
 *      (leka-medusa-order@goco.bz).
 *
 * Both go through the central data-communications routers (Rules 15/16):
 *   - Gmail Router  POST /send_email   (DATA_COMMS_SEND_EMAIL_URL)
 *   - Slack Router  POST /send_slack   (DATA_COMMS_SEND_SLACK_URL)
 *
 * Auth: on Cloud Run we mint a Google-signed ID token from the metadata
 * server with audience = the target URL and send it as a Bearer token. The
 * router verifies signature + audience and asserts the caller SA against its
 * Firestore allowlist (email_sender_allowlist / slack_sender_allowlist).
 *
 * Everything is best-effort — the order is already committed by the time this
 * runs, so a notification failure only logs and never throws.
 */

const METADATA_IDENTITY_URL =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"

async function fetchIdToken(audience: string): Promise<string | null> {
  try {
    const res = await fetch(
      `${METADATA_IDENTITY_URL}?audience=${encodeURIComponent(audience)}`,
      { headers: { "Metadata-Flavor": "Google" } }
    )
    if (!res.ok) {
      console.log(`[notify] metadata token fetch failed: ${res.status}`)
      return null
    }
    return (await res.text()).trim()
  } catch (err: any) {
    console.log(`[notify] metadata server unreachable: ${err?.message}`)
    return null
  }
}

async function postToRouter(url: string, body: Record<string, unknown>): Promise<boolean> {
  const token = await fetchIdToken(url)
  if (!token) return false
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const text = await res.text()
      console.log(`[notify] ${url} -> ${res.status}: ${text}`)
    }
    return res.ok
  } catch (err: any) {
    console.log(`[notify] POST ${url} failed: ${err?.message}`)
    return false
  }
}

function money(amount: number | undefined, currency: string | undefined): string {
  const v = (amount ?? 0) / 100
  const cur = (currency || "").toUpperCase()
  return `${cur} ${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function escapeHtml(s: string): string {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

export default async function orderPlacedHandler({
  event,
  container,
}: SubscriberArgs<{ id: string }>) {
  const orderId = event.data.id

  let order: any
  try {
    const orderService = container.resolve(Modules.ORDER)
    order = await (orderService as any).retrieveOrder(orderId, {
      relations: ["items", "shipping_address", "shipping_methods"],
    })
  } catch (err: any) {
    console.log(`[notify] could not load order ${orderId}: ${err.message}`)
    return
  }

  const items: any[] = order.items || []
  const addr = order.shipping_address || {}
  const customerName = [addr.first_name, addr.last_name].filter(Boolean).join(" ").trim()
  const company = addr.company ? ` (${addr.company})` : ""
  // B2B project context — set on the cart metadata at checkout and copied onto
  // the order at completion (see leka-website catalogs checkout page).
  const meta: any = order.metadata || {}
  const projectName = (meta.project_name ?? "").toString().trim()
  const projectDetails = (meta.project_details ?? "").toString().trim()
  const siteLocation = (meta.site_location ?? "").toString().trim()
  // Multi-brand "bag" correlation — set by the storefront in
  // leka-website/catalogs/src/app/checkout/page.tsx so the team can see which
  // orders belong together. Only meaningful when bag_total_brands > 1.
  // TODO (deferred): a true single-Slack-post-per-bag aggregation would
  // require buffering in Firestore keyed by bag_id with a count-or-timeout
  // gate. Out of scope here — for v1 each order still posts its own message,
  // just with the bag label inline.
  const bagId = (meta.bag_id ?? "").toString().trim()
  const bagBrandIndex = Number(meta.bag_brand_index) || 0
  const bagTotalBrands = Number(meta.bag_total_brands) || 0
  const isMultiBrandBag = !!bagId && bagTotalBrands > 1
  const bagLabel = isMultiBrandBag ? ` (${bagBrandIndex} of ${bagTotalBrands} in bag)` : ""
  // retrieveOrder does not compute order.total — fall back to summing line
  // items (+ shipping) so the alert/email never show a misleading 0.00.
  const itemsSum = items.reduce(
    (s, i) => s + (Number(i.unit_price) || 0) * (Number(i.quantity) || 0),
    0
  )
  const shippingSum = (order.shipping_methods || []).reduce(
    (s: number, m: any) => s + (Number(m.amount) || 0),
    0
  )
  const orderTotal =
    Number(order.total) > 0 ? Number(order.total) : itemsSum + shippingSum
  const totalStr = money(orderTotal, order.currency_code)
  const displayId = order.display_id ?? order.id

  // ---- 1. Slack team alert -> #leka-medusa-order ----
  const slackUrl = process.env.DATA_COMMS_SEND_SLACK_URL
  const channel = process.env.ORDER_NOTIFY_SLACK_CHANNEL || "#leka-medusa-order"
  if (slackUrl) {
    const itemLines = items
      .map((i) => `• ${i.title} ×${i.quantity} — ${money(i.unit_price * i.quantity, order.currency_code)}`)
      .join("\n")
    const shipTo = [addr.address_1, addr.city, addr.province, addr.postal_code, addr.country_code?.toUpperCase()]
      .filter(Boolean)
      .join(", ")
    const projectBlocks: any[] = []
    if (projectName || siteLocation) {
      projectBlocks.push({
        type: "section",
        fields: [
          { type: "mrkdwn", text: `*Project:*\n${projectName || "—"}` },
          { type: "mrkdwn", text: `*Site location:*\n${siteLocation || "—"}` },
        ],
      })
    }
    if (projectDetails) {
      projectBlocks.push({
        type: "section",
        text: { type: "mrkdwn", text: `*Project details:*\n${projectDetails}` },
      })
    }
    await postToRouter(slackUrl, {
      channel,
      text: `:shopping_trolley: New order #${displayId}${bagLabel} — ${totalStr}`,
      blocks: [
        { type: "section", text: { type: "mrkdwn", text: `:shopping_trolley: *New order #${displayId}*${bagLabel} — *${totalStr}*` } },
        {
          type: "section",
          fields: [
            { type: "mrkdwn", text: `*Customer:*\n${customerName || "—"}${company}` },
            { type: "mrkdwn", text: `*Email:*\n${order.email || "—"}` },
            { type: "mrkdwn", text: `*Phone:*\n${addr.phone || "—"}` },
            { type: "mrkdwn", text: `*Ship to:*\n${shipTo || "—"}` },
          ],
        },
        ...projectBlocks,
        { type: "section", text: { type: "mrkdwn", text: `*Items:*\n${itemLines || "—"}` } },
        ...(isMultiBrandBag
          ? [{
              type: "context",
              elements: [{
                type: "mrkdwn",
                text: `Bag \`${bagId}\` · ${bagBrandIndex}/${bagTotalBrands} brands · expect ${bagTotalBrands} alerts total`,
              }],
            }]
          : []),
        { type: "context", elements: [{ type: "mrkdwn", text: `Order ID \`${order.id}\` · payment: manual (invoice follows)` }] },
      ],
      caller: "leka-product-catalogs/order-placed",
      idempotencyKey: `order-slack-${order.id}`,
    })
  } else {
    console.log("[notify] DATA_COMMS_SEND_SLACK_URL unset — skipping Slack")
  }

  // ---- 2. Confirmation email (customer + team bcc) ----
  const emailUrl = process.env.DATA_COMMS_SEND_EMAIL_URL
  const teamEmail = process.env.ORDER_NOTIFY_EMAIL || "leka-medusa-order@goco.bz"
  if (emailUrl) {
    const to = order.email ? [order.email] : [teamEmail]
    const bcc = order.email ? [teamEmail] : []
    const rowsHtml = items
      .map(
        (i) =>
          `<tr><td style="padding:8px 0;border-bottom:1px solid #eee">${escapeHtml(i.title)} &times; ${i.quantity}</td>` +
          `<td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right">${money(i.unit_price * i.quantity, order.currency_code)}</td></tr>`
      )
      .join("")
    const projectHtml =
      projectName || siteLocation || projectDetails
        ? `<div style="background:#FFF9E6;border-radius:12px;padding:12px 16px;margin:0 0 16px;font-size:14px">` +
          (projectName ? `<p style="margin:0 0 4px"><strong>Project:</strong> ${escapeHtml(projectName)}</p>` : "") +
          (siteLocation ? `<p style="margin:0 0 4px"><strong>Site location:</strong> ${escapeHtml(siteLocation)}</p>` : "") +
          (projectDetails ? `<p style="margin:0;white-space:pre-wrap"><strong>Details:</strong> ${escapeHtml(projectDetails)}</p>` : "") +
          `</div>`
        : ""
    const bodyHtml =
      `<div style="font-family:Manrope,Arial,sans-serif;max-width:560px;margin:0 auto;color:#182557">` +
      `<h1 style="color:#8003FF;font-size:22px;margin:0 0 4px">Order confirmed</h1>` +
      `<p style="margin:0 0 16px;color:#555">Thank you${customerName ? `, ${escapeHtml(customerName)}` : ""}! ` +
      `We've received your order <strong>#${displayId}</strong> and our team will be in touch with delivery details and an invoice.</p>` +
      projectHtml +
      `<table style="width:100%;border-collapse:collapse;font-size:14px">${rowsHtml}` +
      `<tr><td style="padding:12px 0;font-weight:700">Total</td>` +
      `<td style="padding:12px 0;text-align:right;font-weight:700;color:#8003FF">${totalStr}</td></tr></table>` +
      `<p style="margin:16px 0 0;font-size:12px;color:#888">Payment is handled manually — an invoice will be sent separately. Reply to this email with any questions.</p>` +
      `<p style="margin:16px 0 0;font-size:12px;color:#aaa">Leka Studio · catalogs.leka.studio</p></div>`
    await postToRouter(emailUrl, {
      to,
      bcc,
      subject: `Leka Studio — Order #${displayId} confirmed${bagLabel}`,
      bodyHtml,
      senderDisplay: "Leka Studio",
      caller: "leka-product-catalogs/order-placed",
      idempotencyKey: `order-email-${order.id}`,
    })
  } else {
    console.log("[notify] DATA_COMMS_SEND_EMAIL_URL unset — skipping email")
  }

  console.log(`[notify] order.placed handled for #${displayId}`)
}

export const config: SubscriberConfig = {
  event: "order.placed",
}
