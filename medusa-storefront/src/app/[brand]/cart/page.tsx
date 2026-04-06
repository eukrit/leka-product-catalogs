"use client"

import { useEffect, useState } from "react"
import { use } from "react"
import Image from "next/image"
import Link from "next/link"
import { notFound } from "next/navigation"
import { medusa, getBrand } from "@/lib/medusa-client"
import { PromoInput } from "@/components/promo-input"

interface CartItem {
  id: string
  title: string
  quantity: number
  unit_price: number
  thumbnail: string | null
  variant: {
    id: string
    sku: string
    product: { handle: string }
  }
}

interface Cart {
  id: string
  items: CartItem[]
  total: number
  subtotal: number
  shipping_total: number
  tax_total: number
  region: { currency_code: string } | null
}

export default function CartPage({
  params,
}: {
  params: Promise<{ brand: string }>
}) {
  const { brand: brandSlug } = use(params)
  const brand = getBrand(brandSlug)
  if (!brand) notFound()

  const [cart, setCart] = useState<Cart | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadCart() {
      const cartId = localStorage.getItem(`cart_${brandSlug}`)
      if (!cartId) {
        setLoading(false)
        return
      }
      try {
        const { cart: fetched } = await medusa.store.cart.retrieve(
          cartId,
          {},
          { "x-publishable-api-key": brand!.publishableKey } as any
        ) as any
        setCart(fetched)
      } catch {
        localStorage.removeItem(`cart_${brandSlug}`)
      }
      setLoading(false)
    }
    loadCart()
  }, [brandSlug, brand])

  async function updateQuantity(lineId: string, quantity: number) {
    if (!cart) return
    try {
      if (quantity <= 0) {
        const { cart: updated } = await medusa.store.cart.deleteLineItem(
          cart.id,
          lineId,
          { "x-publishable-api-key": brand!.publishableKey } as any
        ) as any
        setCart(updated)
      } else {
        const { cart: updated } = await medusa.store.cart.updateLineItem(
          cart.id,
          lineId,
          { quantity },
          { "x-publishable-api-key": brand!.publishableKey } as any
        ) as any
        setCart(updated)
      }
    } catch (err) {
      console.error("Failed to update cart:", err)
    }
  }

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-16 text-center">
        <div className="inline-block w-8 h-8 border-4 border-gray-200 border-t-leka-purple rounded-full animate-spin" />
      </div>
    )
  }

  const items = cart?.items || []
  const currency = cart?.region?.currency_code || "usd"

  return (
    <main className="max-w-4xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold text-leka-navy mb-8">Shopping Cart</h1>

      {items.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-gray-400 mb-4">Your cart is empty</p>
          <Link href={`/${brandSlug}`} className="btn-primary">
            Browse Products
          </Link>
        </div>
      ) : (
        <>
          {/* Cart Items */}
          <div className="space-y-4 mb-8">
            {items.map((item) => (
              <div
                key={item.id}
                className="card flex items-center gap-4 p-4"
              >
                <div className="relative w-20 h-20 bg-gray-50 rounded-button overflow-hidden flex-shrink-0">
                  {item.thumbnail ? (
                    <Image
                      src={item.thumbnail}
                      alt={item.title}
                      fill
                      className="object-contain p-1"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-2xl text-gray-200">
                      📦
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-leka-navy text-sm truncate">
                    {item.title}
                  </div>
                  <div className="text-xs text-gray-400 font-mono">
                    {item.variant?.sku}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => updateQuantity(item.id, item.quantity - 1)}
                    className="w-8 h-8 flex items-center justify-center border border-gray-200 rounded text-gray-500 hover:border-leka-purple"
                  >
                    -
                  </button>
                  <span className="w-8 text-center text-sm font-semibold">
                    {item.quantity}
                  </span>
                  <button
                    onClick={() => updateQuantity(item.id, item.quantity + 1)}
                    className="w-8 h-8 flex items-center justify-center border border-gray-200 rounded text-gray-500 hover:border-leka-purple"
                  >
                    +
                  </button>
                </div>
                <div className="text-right min-w-[80px]">
                  <div className="font-semibold text-leka-navy">
                    ${((item.unit_price * item.quantity) / 100).toFixed(2)}
                  </div>
                  <div className="text-xs text-gray-400">
                    ${(item.unit_price / 100).toFixed(2)} each
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Promo Code */}
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-leka-navy mb-2">Promo Code</h3>
            <PromoInput
              brandSlug={brandSlug}
              cartId={cart!.id}
              onApplied={() => {
                if (!cart) return
                medusa.store.cart.retrieve(
                  cart.id,
                  {},
                  { "x-publishable-api-key": brand!.publishableKey } as any
                ).then((res: any) => setCart(res.cart))
              }}
            />
          </div>

          {/* Summary */}
          <div className="card p-6">
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Subtotal</span>
                <span className="font-semibold">
                  ${((cart?.subtotal || 0) / 100).toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Shipping</span>
                <span className="font-semibold">
                  {cart?.shipping_total
                    ? `$${(cart.shipping_total / 100).toFixed(2)}`
                    : "Calculated at checkout"}
                </span>
              </div>
              <div className="border-t pt-2 flex justify-between text-lg">
                <span className="font-semibold text-leka-navy">Total</span>
                <span className="font-bold text-leka-purple">
                  ${((cart?.total || 0) / 100).toFixed(2)}
                </span>
              </div>
            </div>
            <Link
              href={`/${brandSlug}/checkout`}
              className="btn-primary w-full mt-6"
            >
              Proceed to Checkout
            </Link>
          </div>
        </>
      )}
    </main>
  )
}
