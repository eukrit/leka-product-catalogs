import type { SubscriberArgs, SubscriberConfig } from "@medusajs/framework"
import { Modules } from "@medusajs/framework/utils"

/**
 * Send notification when an order is placed.
 * Requires a notification provider (e.g., SendGrid) configured in medusa-config.
 * Falls back to console logging if no provider is set up.
 */
export default async function orderPlacedHandler({
  event,
  container,
}: SubscriberArgs<{ id: string }>) {
  const orderId = event.data.id

  try {
    const orderService = container.resolve(Modules.ORDER)
    const order = await (orderService as any).retrieveOrder(orderId)

    const notificationService = container.resolve(Modules.NOTIFICATION)

    await (notificationService as any).createNotifications({
      to: order.email,
      channel: "email",
      template: "order-confirmation",
      data: {
        order_id: order.id,
        display_id: order.display_id,
        email: order.email,
        items: order.items?.map((item: any) => ({
          title: item.title,
          quantity: item.quantity,
          unit_price: item.unit_price,
        })),
        total: order.total,
        currency_code: order.currency_code,
        shipping_address: order.shipping_address,
      },
    })

    console.log(`[notification] Order confirmation sent for order ${order.display_id} to ${order.email}`)
  } catch (err: any) {
    // Notification provider may not be configured yet — log and continue
    console.log(`[notification] Could not send order confirmation for ${orderId}: ${err.message}`)
  }
}

export const config: SubscriberConfig = {
  event: "order.placed",
}
