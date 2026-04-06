"use client"

import { useEffect, useState } from "react"
import { use } from "react"
import Link from "next/link"
import { notFound } from "next/navigation"
import { medusa, getBrand } from "@/lib/medusa-client"

export default function AccountPage({
  params,
}: {
  params: Promise<{ brand: string }>
}) {
  const { brand: brandSlug } = use(params)
  const brand = getBrand(brandSlug)
  if (!brand) notFound()

  const [customer, setCustomer] = useState<any>(null)
  const [orders, setOrders] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [loginForm, setLoginForm] = useState({ email: "", password: "" })
  const [isRegistering, setIsRegistering] = useState(false)
  const [registerForm, setRegisterForm] = useState({
    email: "",
    password: "",
    first_name: "",
    last_name: "",
  })

  useEffect(() => {
    loadCustomer()
  }, [])

  async function loadCustomer() {
    try {
      const { customer: c } = await medusa.store.customer.retrieve(
        {},
        { "x-publishable-api-key": brand!.publishableKey } as any
      ) as any
      setCustomer(c)
      await loadOrders()
    } catch {
      // Not logged in
    }
    setLoading(false)
  }

  async function loadOrders() {
    try {
      const { orders: o } = await medusa.store.order.list(
        { limit: 20 },
        { "x-publishable-api-key": brand!.publishableKey } as any
      ) as any
      setOrders(o || [])
    } catch (err) {
      console.error("Failed to load orders:", err)
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    try {
      await medusa.auth.login("customer", "emailpass", {
        email: loginForm.email,
        password: loginForm.password,
      })
      await loadCustomer()
    } catch (err) {
      console.error("Login failed:", err)
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    try {
      const token = await medusa.auth.register("customer", "emailpass", {
        email: registerForm.email,
        password: registerForm.password,
      })
      // Create customer profile
      await medusa.store.customer.create(
        {
          email: registerForm.email,
          first_name: registerForm.first_name,
          last_name: registerForm.last_name,
        },
        { "x-publishable-api-key": brand!.publishableKey } as any
      )
      await loadCustomer()
    } catch (err) {
      console.error("Registration failed:", err)
    }
  }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-16 text-center">
        <div className="inline-block w-8 h-8 border-4 border-gray-200 border-t-leka-purple rounded-full animate-spin" />
      </div>
    )
  }

  // Not logged in — show login/register
  if (!customer) {
    return (
      <main className="max-w-md mx-auto px-6 py-8">
        <h1 className="text-2xl font-bold text-leka-navy mb-8 text-center">
          {isRegistering ? "Create Account" : "Sign In"}
        </h1>

        {!isRegistering ? (
          <form onSubmit={handleLogin} className="card p-6 space-y-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Email</label>
              <input
                type="email"
                value={loginForm.email}
                onChange={(e) => setLoginForm({ ...loginForm, email: e.target.value })}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Password</label>
              <input
                type="password"
                value={loginForm.password}
                onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                required
              />
            </div>
            <button type="submit" className="btn-primary w-full">
              Sign In
            </button>
            <button
              type="button"
              onClick={() => setIsRegistering(true)}
              className="text-sm text-leka-purple hover:underline w-full text-center"
            >
              Create an account
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister} className="card p-6 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">First Name</label>
                <input
                  type="text"
                  value={registerForm.first_name}
                  onChange={(e) => setRegisterForm({ ...registerForm, first_name: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                  required
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Last Name</label>
                <input
                  type="text"
                  value={registerForm.last_name}
                  onChange={(e) => setRegisterForm({ ...registerForm, last_name: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                  required
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Email</label>
              <input
                type="email"
                value={registerForm.email}
                onChange={(e) => setRegisterForm({ ...registerForm, email: e.target.value })}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Password</label>
              <input
                type="password"
                value={registerForm.password}
                onChange={(e) => setRegisterForm({ ...registerForm, password: e.target.value })}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-button text-sm focus:outline-none focus:border-leka-purple"
                required
              />
            </div>
            <button type="submit" className="btn-primary w-full">
              Create Account
            </button>
            <button
              type="button"
              onClick={() => setIsRegistering(false)}
              className="text-sm text-leka-purple hover:underline w-full text-center"
            >
              Already have an account? Sign in
            </button>
          </form>
        )}
      </main>
    )
  }

  // Logged in — show account + orders
  return (
    <main className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-leka-navy">
            {customer.first_name} {customer.last_name}
          </h1>
          <p className="text-sm text-gray-500">{customer.email}</p>
        </div>
      </div>

      {/* Quick Links */}
      <div className="flex gap-3 mb-8">
        <Link
          href={`/${brandSlug}/account/quotes`}
          className="card p-4 flex-1 hover:ring-2 hover:ring-leka-purple/20 text-center"
        >
          <div className="text-2xl mb-1">📋</div>
          <div className="text-sm font-semibold text-leka-navy">Quotations</div>
          <div className="text-xs text-gray-400">Draft orders & quotes</div>
        </Link>
        <Link
          href={`/${brandSlug}`}
          className="card p-4 flex-1 hover:ring-2 hover:ring-leka-purple/20 text-center"
        >
          <div className="text-2xl mb-1">🛍️</div>
          <div className="text-sm font-semibold text-leka-navy">Browse</div>
          <div className="text-xs text-gray-400">Product catalog</div>
        </Link>
      </div>

      <h2 className="text-lg font-semibold text-leka-navy mb-4">
        Order History
      </h2>

      {orders.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="text-gray-400">No orders yet</p>
          <Link href={`/${brandSlug}`} className="btn-primary mt-4 inline-flex">
            Browse Products
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {orders.map((order) => (
            <Link
              key={order.id}
              href={`/${brandSlug}/account/orders/${order.id}`}
              className="card p-4 flex items-center justify-between hover:ring-2 hover:ring-leka-purple/20"
            >
              <div>
                <div className="font-semibold text-leka-navy text-sm">
                  Order #{order.display_id}
                </div>
                <div className="text-xs text-gray-400">
                  {new Date(order.created_at).toLocaleDateString()}
                </div>
              </div>
              <div className="text-right">
                <div className="font-semibold text-leka-purple">
                  ${((order.total || 0) / 100).toFixed(2)}
                </div>
                <div className="text-xs text-gray-400 capitalize">
                  {order.fulfillment_status || "pending"}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  )
}
