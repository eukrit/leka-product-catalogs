"use client"

import { useEffect, useState } from "react"
import { use } from "react"
import { notFound, useRouter } from "next/navigation"
import { medusa, getBrand } from "@/lib/medusa-client"
import { getCartId, clearCart } from "@/lib/cart"

interface CheckoutForm {
  email: string
  first_name: string
  last_name: string
  company: string
  address_1: string
  address_2: string
  city: string
  province: string
  postal_code: string
  country_code: string
  phone: string
}

export default function CheckoutPage({
  params,
}: {
  params: Promise<{ brand: string }>
}) {
  const { brand: brandSlug } = use(params)
  const brand = getBrand(brandSlug)
  if (!brand) notFound()

  const router = useRouter()
  const [step, setStep] = useState<"shipping" | "review" | "complete">("shipping")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const [cart, setCart] = useState<any>(null)
  const [form, setForm] = useState<CheckoutForm>({
    email: "",
    first_name: "",
    last_name: "",
    company: "",
    address_1: "",
    address_2: "",
    city: "",
    province: "",
    postal_code: "",
    country_code: "th",
    phone: "",
  })

  useEffect(() => {
    async function loadCart() {
      const cartId = getCartId(brandSlug)
      if (!cartId) {
        router.push(`/${brandSlug}/cart`)
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
        router.push(`/${brandSlug}/cart`)
      }
    }
    loadCart()
  }, [brandSlug, brand, router])

  function updateField(field: keyof CheckoutForm, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  async function handleSubmitShipping() {
    if (!cart) return
    setSubmitting(true)
    setError("")
    try {
      await medusa.store.cart.update(
        cart.id,
        {
          email: form.email,
          shipping_address: {
            first_name: form.first_name,
            last_name: form.last_name,
            company: form.company,
            address_1: form.address_1,
            address_2: form.address_2,
            city: form.city,
            province: form.province,
            postal_code: form.postal_code,
            country_code: form.country_code,
            phone: form.phone,
          },
        },
        { "x-publishable-api-key": brand!.publishableKey } as any
      )
      setStep("review")
    } catch (err: any) {
      const msg = err?.response?.data?.message || "Failed to save shipping address. Please check your details."
      setError(msg)
    }
    setSubmitting(false)
  }

  async function handlePlaceOrder() {
    if (!cart) return
    setSubmitting(true)
    try {
      const { type, order } = await medusa.store.cart.complete(
        cart.id,
        {},
        { "x-publishable-api-key": brand!.publishableKey } as any
      ) as any

      if (type === "order") {
        clearCart(brandSlug)
        setStep("complete")
      }
    } catch (err: any) {
      const msg = err?.response?.data?.message || "Failed to place order. Please try again."
      setError(msg)
    }
    setSubmitting(false)
  }

  if (!cart) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-16 text-center">
        <div className="inline-block w-8 h-8 border-4 border-gray-200 border-t-leka-purple rounded-full animate-spin" />
      </div>
    )
  }

  if (step === "complete") {
    return (
      <main className="max-w-2xl mx-auto px-6 py-16 text-center">
        <div className="text-4xl mb-4">&#10003;</div>
        <h1 className="text-2xl font-bold text-leka-navy mb-2">
          Order Placed Successfully
        </h1>
        <p className="text-gray-500 mb-6">
          Thank you for your order. We will contact you with shipping details.
        </p>
        <button
          onClick={() => router.push(`/${brandSlug}`)}
          className="btn-primary"
        >
          Continue Shopping
        </button>
      </main>
    )
  }

  return (
    <main className="max-w-2xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold text-leka-navy mb-8">Checkout</h1>

      {/* Steps indicator */}
      <div className="flex items-center gap-4 mb-8 text-sm">
        <span className={step === "shipping" ? "font-bold text-leka-purple" : "text-gray-400"}>
          1. Shipping
        </span>
        <span className="text-gray-300">&rarr;</span>
        <span className={step === "review" ? "font-bold text-leka-purple" : "text-gray-400"}>
          2. Review & Pay
        </span>
      </div>

      {step === "shipping" && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-leka-navy mb-4">
            Shipping Address
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => updateField("email", e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">First Name</label>
              <input
                type="text"
                value={form.first_name}
                onChange={(e) => updateField("first_name", e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Last Name</label>
              <input
                type="text"
                value={form.last_name}
                onChange={(e) => updateField("last_name", e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                required
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Company</label>
              <input
                type="text"
                value={form.company}
                onChange={(e) => updateField("company", e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Address</label>
              <input
                type="text"
                value={form.address_1}
                onChange={(e) => updateField("address_1", e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">City</label>
              <input
                type="text"
                value={form.city}
                onChange={(e) => updateField("city", e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Province / State</label>
              <input
                type="text"
                value={form.province}
                onChange={(e) => updateField("province", e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Postal Code</label>
              <input
                type="text"
                value={form.postal_code}
                onChange={(e) => updateField("postal_code", e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Country</label>
              <select
                value={form.country_code}
                onChange={(e) => updateField("country_code", e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
              >
                <option value="th">Thailand</option>
                <option value="us">United States</option>
                <option value="cn">China</option>
                <option value="pl">Poland</option>
                <option value="sg">Singapore</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Phone</label>
              <input
                type="tel"
                value={form.phone}
                onChange={(e) => updateField("phone", e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
              />
            </div>
          </div>
          {error && (
            <p className="text-sm text-red-500 mt-4 p-3 bg-red-50 rounded-button">{error}</p>
          )}
          <button
            onClick={handleSubmitShipping}
            disabled={submitting || !form.email || !form.first_name || !form.address_1}
            className="btn-primary w-full mt-4 disabled:opacity-50"
          >
            {submitting ? "Saving..." : "Continue to Review"}
          </button>
        </div>
      )}

      {step === "review" && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-leka-navy mb-4">
            Order Review
          </h2>
          <div className="space-y-3 mb-6">
            {cart.items?.map((item: any) => (
              <div key={item.id} className="flex justify-between text-sm">
                <span>
                  {item.title} &times; {item.quantity}
                </span>
                <span className="font-semibold">
                  ${((item.unit_price * item.quantity) / 100).toFixed(2)}
                </span>
              </div>
            ))}
          </div>
          <div className="border-t pt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Subtotal</span>
              <span>${((cart.subtotal || 0) / 100).toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-lg font-bold">
              <span className="text-leka-navy">Total</span>
              <span className="text-leka-purple">
                ${((cart.total || 0) / 100).toFixed(2)}
              </span>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-4">
            Payment: Manual (invoice will be sent separately)
          </p>
          {error && (
            <p className="text-sm text-red-500 mt-4 p-3 bg-red-50 rounded-button">{error}</p>
          )}
          <div className="flex gap-3 mt-4">
            <button
              onClick={() => setStep("shipping")}
              className="btn-secondary flex-1"
            >
              Back
            </button>
            <button
              onClick={handlePlaceOrder}
              disabled={submitting}
              className="btn-primary flex-1 disabled:opacity-50"
            >
              {submitting ? "Placing Order..." : "Place Order"}
            </button>
          </div>
        </div>
      )}
    </main>
  )
}
