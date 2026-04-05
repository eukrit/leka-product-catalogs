import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "Leka Product Catalogs",
  description: "Multi-brand product catalog by GO Corporation",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
