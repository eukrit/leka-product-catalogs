"use client"

import { useEffect, useState } from "react"
import { use } from "react"
import Link from "next/link"
import { notFound } from "next/navigation"
import { medusa, getBrand } from "@/lib/medusa-client"

export default function OrderDetailPage({
  params,
}: {
  params: Promise<{ brand: string; id: string }>
}) {
  const { brand: brandSlug, id: orderId } = use(params)
  const brand = getBrand(brandSlug)
  if (!brand) notFound()

  const [order, setOrder] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadOrder() {
      try {
        const { order: o } = await medusa.store.order.retrieve(
          orderId,
          {},
          { "x-publishable-api-key": brand!.publishableKey } as any
        ) as any
        setOrder(o)
      } catch (err) {
        console.error("Failed to load order:", err)
      }
      setLoading(false)
    }
    loadOrder()
  }, [orderId, brand])

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-16 text-center">
        <div className="inline-block w-8 h-8 border-4 border-gray-200 border-t-leka-purple rounded-full animate-spin" />
      </div>
    )
  }

  if (!order) return notFound()

  const shipping = order.shipping_address || {}

  return (
    <main className="max-w-2xl mx-auto px-6 py-8">
      <Link
        href={`/${brandSlug}/account`}
        className="text-sm text-gray-400 hover:text-leka-purple mb-4 inline-block"
      >
        &larr; Back to Account
      </Link>

      <h1 className="text-2xl font-bold text-leka-navy mb-2">
        Order #{order.display_id}
      </h1>
      <p className="text-sm text-gray-500 mb-8">
        Placed on {new Date(order.created_at).toLocaleDateString()}
      </p>

      {/* Items */}
      <div className="card p-6 mb-6">
        <h2 className="text-lg font-semibold text-leka-navy mb-4">Items</h2>
        <div className="space-y-3">
          {order.items?.map((item: any) => (
            <div key={item.id} className="flex justify-between text-sm">
              <div>
                <span className="font-medium">{item.title}</span>
                <span className="text-gray-400 ml-2">&times; {item.quantity}</span>
              </div>
              <span className="font-semibold">
                ${((item.unit_price * item.quantity) / 100).toFixed(2)}
              </span>
            </div>
          ))}
        </div>
        <div className="border-t mt-4 pt-4 flex justify-between text-lg font-bold">
          <span className="text-leka-navy">Total</span>
          <span className="text-leka-purple">
            ${((order.total || 0) / 100).toFixed(2)}
          </span>
        </div>
      </div>

      {/* Shipping */}
      <div className="card p-6 mb-6">
        <h2 className="text-lg font-semibold text-leka-navy mb-4">
          Shipping Address
        </h2>
        <div className="text-sm text-gray-600 space-y-1">
          <p className="font-medium">
            {shipping.first_name} {shipping.last_name}
          </p>
          {shipping.company && <p>{shipping.company}</p>}
          <p>{shipping.address_1}</p>
          {shipping.address_2 && <p>{shipping.address_2}</p>}
          <p>
            {shipping.city}, {shipping.province} {shipping.postal_code}
          </p>
          <p>{shipping.country_code?.toUpperCase()}</p>
        </div>
      </div>

      {/* Status */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-leka-navy mb-4">Status</h2>
        <div className="flex gap-4 text-sm">
          <div>
            <span className="text-gray-400">Payment:</span>{" "}
            <span className="font-medium capitalize">
              {order.payment_status || "pending"}
            </span>
          </div>
          <div>
            <span className="text-gray-400">Fulfillment:</span>{" "}
            <span className="font-medium capitalize">
              {order.fulfillment_status || "pending"}
            </span>
          </div>
        </div>
      </div>
    </main>
  )
}
