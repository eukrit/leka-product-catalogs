"use client"

import { useState } from "react"
import { medusa, getBrand } from "@/lib/medusa-client"

interface PromoInputProps {
  brandSlug: string
  cartId: string
  onApplied: () => void
}

export function PromoInput({ brandSlug, cartId, onApplied }: PromoInputProps) {
  const brand = getBrand(brandSlug)
  const [code, setCode] = useState("")
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")

  async function handleApply() {
    if (!code.trim() || !brand) return
    setApplying(true)
    setError("")
    setSuccess("")

    try {
      await medusa.store.cart.update(
        cartId,
        { promo_codes: [code.trim()] },
        { "x-publishable-api-key": brand.publishableKey } as any
      )
      setSuccess(`Code "${code}" applied!`)
      setCode("")
      onApplied()
    } catch (err: any) {
      setError(err?.response?.data?.message || "Invalid promo code")
    }
    setApplying(false)
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          type="text"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="Promo code"
          className="flex-1 px-3 py-2 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
          onKeyDown={(e) => e.key === "Enter" && handleApply()}
        />
        <button
          onClick={handleApply}
          disabled={applying || !code.trim()}
          className="btn-secondary text-sm px-4 py-2 disabled:opacity-50"
        >
          {applying ? "..." : "Apply"}
        </button>
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
      {success && <p className="text-xs text-green-600">{success}</p>}
    </div>
  )
}
