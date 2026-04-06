"use client"

import { useEffect, useState } from "react"
import { use } from "react"
import Link from "next/link"
import { notFound } from "next/navigation"
import { medusa, getBrand } from "@/lib/medusa-client"

/**
 * Draft Orders / Quotations page.
 * Displays draft orders created by admin for this customer.
 * Customer can review and confirm draft orders.
 */
export default function QuotesPage({
  params,
}: {
  params: Promise<{ brand: string }>
}) {
  const { brand: brandSlug } = use(params)
  const brand = getBrand(brandSlug)
  if (!brand) notFound()

  const [drafts, setDrafts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadDrafts() {
      try {
        // Draft orders are fetched via the store API once Medusa v2.10+ is configured
        const { draft_orders } = (await medusa.store.order.list(
          { status: ["pending"], limit: 50 },
          { "x-publishable-api-key": brand!.publishableKey } as any
        )) as any
        setDrafts(draft_orders || [])
      } catch (err) {
        console.error("Failed to load draft orders:", err)
      }
      setLoading(false)
    }
    loadDrafts()
  }, [brand])

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-16 text-center">
        <div className="inline-block w-8 h-8 border-4 border-gray-200 border-t-leka-purple rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <main className="max-w-4xl mx-auto px-6 py-8">
      <nav className="text-sm text-gray-400 mb-6">
        <Link href={`/${brandSlug}/account`} className="hover:text-leka-purple">
          Account
        </Link>
        <span className="mx-2">/</span>
        <span className="text-leka-navy">Quotations</span>
      </nav>

      <h1 className="text-2xl font-bold text-leka-navy mb-2">Quotations</h1>
      <p className="text-sm text-gray-500 mb-8">
        Draft orders and quotation requests from your account manager.
      </p>

      {drafts.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="text-gray-400 mb-2">No quotations yet</p>
          <p className="text-sm text-gray-400">
            Contact your account manager to request a quotation.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {drafts.map((draft) => (
            <div
              key={draft.id}
              className="card p-4"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold text-leka-navy text-sm">
                    Quote #{draft.display_id || draft.id.slice(0, 8)}
                  </div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    {draft.items?.length || 0} items &middot;{" "}
                    {new Date(draft.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-semibold text-leka-purple">
                    ${((draft.total || 0) / 100).toFixed(2)}
                  </div>
                  <span className="badge badge-amber text-xs mt-1">
                    Pending Review
                  </span>
                </div>
              </div>

              {/* Line items */}
              <div className="mt-3 space-y-1">
                {draft.items?.slice(0, 5).map((item: any) => (
                  <div key={item.id} className="flex justify-between text-xs text-gray-500">
                    <span>{item.title} &times; {item.quantity}</span>
                    <span>${((item.unit_price * item.quantity) / 100).toFixed(2)}</span>
                  </div>
                ))}
                {(draft.items?.length || 0) > 5 && (
                  <div className="text-xs text-gray-400">
                    +{draft.items.length - 5} more items
                  </div>
                )}
              </div>

              <div className="mt-3 flex gap-2">
                <button className="btn-primary text-xs px-3 py-1.5">
                  Accept & Place Order
                </button>
                <button className="btn-secondary text-xs px-3 py-1.5">
                  Request Changes
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
