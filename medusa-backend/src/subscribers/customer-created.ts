import type { SubscriberArgs, SubscriberConfig } from "@medusajs/framework"
import { Modules } from "@medusajs/framework/utils"

/**
 * Send welcome notification when a customer registers.
 */
export default async function customerCreatedHandler({
  event,
  container,
}: SubscriberArgs<{ id: string }>) {
  const customerId = event.data.id

  try {
    const customerService = container.resolve(Modules.CUSTOMER)
    const customer = await (customerService as any).retrieveCustomer(customerId)

    const notificationService = container.resolve(Modules.NOTIFICATION)

    await (notificationService as any).createNotifications({
      to: customer.email,
      channel: "email",
      template: "customer-welcome",
      data: {
        first_name: customer.first_name,
        last_name: customer.last_name,
        email: customer.email,
      },
    })

    console.log(`[notification] Welcome email sent to ${customer.email}`)
  } catch (err: any) {
    console.log(`[notification] Could not send welcome email for ${customerId}: ${err.message}`)
  }
}

export const config: SubscriberConfig = {
  event: "customer.created",
}
