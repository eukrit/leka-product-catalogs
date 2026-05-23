import type { SubscriberArgs, SubscriberConfig } from "@medusajs/framework"
import { Modules } from "@medusajs/framework/utils"

/**
 * On `order.placed` (draft orders trigger the same event family in Medusa v2):
 *   if order.metadata.proposal_builder === true, post a Slack alert to
 *   #leka-medusa-proposal so the proposal_engine operator picks up the
 *   draft_order_id and pastes it into projects/<id>/config.yaml.
 *
 * Best-effort — the draft order is already committed by the time this runs,
 * so a Slack failure only logs and never throws.
 *
 * Subscribed event: `order.placed` (covers draft orders too in v2; we filter
 * via `metadata.proposal_builder`). If Medusa v2 emits `draft-order.created`
 * separately in your version, add a second subscriber with that event name.
 */

const METADATA_IDENTITY_URL =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"

async function fetchIdToken(audience: string): Promise<string | null> {
  try {
    const r = await fetch(
      `${METADATA_IDENTITY_URL}?audience=${encodeURIComponent(audience)}`,
      { headers: { "Metadata-Flavor": "Google" } }
    )
    if (!r.ok) return null
    return (await r.text()).trim()
  } catch {
    return null
  }
}

async function postToSlackRouter(url: string, body: Record<string, unknown>): Promise<void> {
  const token = await fetchIdToken(url)
  if (!token) {
    console.log(`[proposal-created] no metadata token; skipping Slack`)
    return
  }
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    if (!r.ok) {
      const text = await r.text()
      console.log(`[proposal-created] ${url} -> ${r.status}: ${text}`)
    }
  } catch (err: any) {
    console.log(`[proposal-created] POST ${url} failed: ${err?.message}`)
  }
}

function money(amount: number | undefined, currency: string | undefined): string {
  const v = (amount ?? 0) / 100
  const cur = (currency || "").toUpperCase()
  return `${cur} ${v.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

export default async function proposalCreatedHandler({
  event,
  container,
}: SubscriberArgs<{ id: string }>) {
  const orderId = event.data.id

  let order: any
  try {
    const orderService = container.resolve(Modules.ORDER)
    order = await (orderService as any).retrieveOrder(orderId, {
      relations: ["items"],
    })
  } catch (err: any) {
    console.log(`[proposal-created] could not load order ${orderId}: ${err.message}`)
    return
  }

  const meta: any = order.metadata || {}
  if (meta.proposal_builder !== true) {
    return // not a proposal — skip
  }

  const items: any[] = order.items || []
  const itemsSum = items.reduce(
    (s, i) => s + (Number(i.unit_price) || 0) * (Number(i.quantity) || 0),
    0
  )
  const total = money(itemsSum, order.currency_code)
  const displayId = order.display_id ?? order.id
  const projectId = (meta.project_id ?? "").toString().trim() || "(no project_id)"
  const projectName = (meta.project_name ?? "").toString().trim()
  const siteLocation = (meta.site_location ?? "").toString().trim()

  const slackUrl = process.env.DATA_COMMS_SEND_SLACK_URL
  const channel = process.env.PROPOSAL_NOTIFY_SLACK_CHANNEL || "#leka-medusa-proposal"
  if (!slackUrl) {
    console.log(`[proposal-created] DATA_COMMS_SEND_SLACK_URL unset — skipping`)
    return
  }

  const itemLines = items
    .map(
      (i) =>
        `• ${i.title} ×${i.quantity} — ${money(
          (i.unit_price || 0) * (i.quantity || 0),
          order.currency_code
        )}`
    )
    .join("\n")

  const fields: Array<Record<string, string>> = [
    { type: "mrkdwn", text: `*Project ID:*\n\`${projectId}\`` },
    { type: "mrkdwn", text: `*Total:*\n${total}` },
  ]
  if (projectName) fields.push({ type: "mrkdwn", text: `*Project name:*\n${projectName}` })
  if (siteLocation) fields.push({ type: "mrkdwn", text: `*Site:*\n${siteLocation}` })

  await postToSlackRouter(slackUrl, {
    channel,
    text: `:memo: New proposal draft #${displayId} — ${total}`,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `:memo: *New proposal draft #${displayId}* — *${total}*`,
        },
      },
      { type: "section", fields },
      {
        type: "section",
        text: { type: "mrkdwn", text: `*Items:*\n${itemLines || "—"}` },
      },
      {
        type: "context",
        elements: [
          {
            type: "mrkdwn",
            text: `Draft order ID \`${order.id}\` · paste into \`projects/${projectId}/config.yaml\` → \`boq.sources: [{kind: medusa, draft_order_ids: [<id>]}]\` then \`python -m proposal_engine render projects/${projectId}/config.yaml\``,
          },
        ],
      },
    ],
    caller: "leka-product-catalogs/proposal-created",
    idempotencyKey: `proposal-slack-${order.id}`,
  })

  console.log(`[proposal-created] notified for #${displayId} (${projectId})`)
}

export const config: SubscriberConfig = {
  event: "order.placed",
}
