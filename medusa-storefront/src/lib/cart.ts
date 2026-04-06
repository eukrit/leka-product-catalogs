"use client"

import { medusa, getBrand } from "./medusa-client"

/**
 * Cart state management — one cart per brand, persisted in localStorage.
 */

function cartKey(brandSlug: string) {
  return `leka_cart_${brandSlug}`
}

export async function getOrCreateCart(brandSlug: string): Promise<string> {
  const brand = getBrand(brandSlug)
  if (!brand) throw new Error(`Unknown brand: ${brandSlug}`)

  const existing = localStorage.getItem(cartKey(brandSlug))
  if (existing) {
    try {
      // Verify cart still exists
      await medusa.store.cart.retrieve(
        existing,
        {},
        { "x-publishable-api-key": brand.publishableKey } as any
      )
      return existing
    } catch {
      localStorage.removeItem(cartKey(brandSlug))
    }
  }

  // Create new cart
  const { cart } = (await medusa.store.cart.create(
    {},
    { "x-publishable-api-key": brand.publishableKey } as any
  )) as any
  localStorage.setItem(cartKey(brandSlug), cart.id)
  return cart.id
}

export async function addToCart(
  brandSlug: string,
  variantId: string,
  quantity: number = 1
) {
  const brand = getBrand(brandSlug)
  if (!brand) throw new Error(`Unknown brand: ${brandSlug}`)

  const cartId = await getOrCreateCart(brandSlug)
  const { cart } = (await medusa.store.cart.createLineItem(
    cartId,
    { variant_id: variantId, quantity },
    { "x-publishable-api-key": brand.publishableKey } as any
  )) as any
  return cart
}

export async function getCart(brandSlug: string) {
  const brand = getBrand(brandSlug)
  if (!brand) return null

  const cartId = localStorage.getItem(cartKey(brandSlug))
  if (!cartId) return null

  try {
    const { cart } = (await medusa.store.cart.retrieve(
      cartId,
      {},
      { "x-publishable-api-key": brand.publishableKey } as any
    )) as any
    return cart
  } catch {
    localStorage.removeItem(cartKey(brandSlug))
    return null
  }
}

export function getCartId(brandSlug: string): string | null {
  return localStorage.getItem(cartKey(brandSlug))
}

export function clearCart(brandSlug: string) {
  localStorage.removeItem(cartKey(brandSlug))
}
