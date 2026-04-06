"use client"

import { useEffect, useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { medusa, getBrand } from "@/lib/medusa-client"

interface CartDrawerProps {
  brandSlug: string
  isOpen: boolean
  onClose: () => void
  cartId: string | null
  onCartUpdate: () => void
}

export function CartDrawer({
  brandSlug,
  isOpen,
  onClose,
  cartId,
  onCartUpdate,
}: CartDrawerProps) {
  const brand = getBrand(brandSlug)
  const [cart, setCart] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!isOpen || !cartId || !brand) return
    setLoading(true)
    medusa.store.cart
      .retrieve(
        cartId,
        {},
        { "x-publishable-api-key": brand.publishableKey } as any
      )
      .then((res: any) => setCart(res.cart))
      .catch(() => setCart(null))
      .finally(() => setLoading(false))
  }, [isOpen, cartId, brand])

  async function updateQuantity(lineId: string, quantity: number) {
    if (!cart || !brand) return
    try {
      if (quantity <= 0) {
        const { cart: updated } = (await medusa.store.cart.deleteLineItem(
          cart.id,
          lineId,
          { "x-publishable-api-key": brand.publishableKey } as any
        )) as any
        setCart(updated)
      } else {
        const { cart: updated } = (await medusa.store.cart.updateLineItem(
          cart.id,
          lineId,
          { quantity },
          { "x-publishable-api-key": brand.publishableKey } as any
        )) as any
        setCart(updated)
      }
      onCartUpdate()
    } catch (err) {
      console.error("Failed to update cart:", err)
    }
  }

  const items = cart?.items || []
  const itemCount = items.reduce((sum: number, i: any) => sum + i.quantity, 0)

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40 transition-opacity"
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className={`fixed top-0 right-0 h-full w-full max-w-md bg-white shadow-xl z-50 transform transition-transform duration-300 ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-bold text-leka-navy">
            Cart ({itemCount})
          </h2>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-leka-navy"
          >
            &times;
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4" style={{ maxHeight: "calc(100vh - 160px)" }}>
          {loading ? (
            <div className="text-center py-8">
              <div className="inline-block w-6 h-6 border-3 border-gray-200 border-t-leka-purple rounded-full animate-spin" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-400 text-sm">Your cart is empty</p>
              <button onClick={onClose} className="btn-primary mt-4 text-sm px-4 py-2">
                Continue Shopping
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {items.map((item: any) => (
                <div key={item.id} className="flex gap-3 p-2 rounded-button bg-gray-50">
                  <div className="relative w-16 h-16 bg-white rounded overflow-hidden flex-shrink-0">
                    {item.thumbnail ? (
                      <Image
                        src={item.thumbnail}
                        alt={item.title}
                        fill
                        className="object-contain p-1"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-xl text-gray-200">
                        📦
                      </div>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-leka-navy truncate">
                      {item.title}
                    </div>
                    <div className="text-xs text-gray-400">{item.variant?.sku}</div>
                    <div className="flex items-center gap-2 mt-1">
                      <button
                        onClick={() => updateQuantity(item.id, item.quantity - 1)}
                        className="w-6 h-6 flex items-center justify-center border rounded text-xs text-gray-500 hover:border-leka-purple"
                      >
                        -
                      </button>
                      <span className="text-xs font-semibold w-4 text-center">
                        {item.quantity}
                      </span>
                      <button
                        onClick={() => updateQuantity(item.id, item.quantity + 1)}
                        className="w-6 h-6 flex items-center justify-center border rounded text-xs text-gray-500 hover:border-leka-purple"
                      >
                        +
                      </button>
                    </div>
                  </div>
                  <div className="text-sm font-semibold text-leka-navy">
                    ${((item.unit_price * item.quantity) / 100).toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        {items.length > 0 && (
          <div className="border-t p-4 space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Subtotal</span>
              <span className="font-bold text-leka-navy">
                ${((cart?.subtotal || 0) / 100).toFixed(2)}
              </span>
            </div>
            <Link
              href={`/${brandSlug}/cart`}
              onClick={onClose}
              className="btn-secondary w-full text-center text-sm"
            >
              View Cart
            </Link>
            <Link
              href={`/${brandSlug}/checkout`}
              onClick={onClose}
              className="btn-primary w-full text-center text-sm"
            >
              Checkout
            </Link>
          </div>
        )}
      </div>
    </>
  )
}
