import type { Metadata } from "next"
import {
  Inter,
  Lato,
  Montserrat,
  Nunito,
  Open_Sans,
  Poppins,
  Roboto,
} from "next/font/google"
import "./globals.css"

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-poppins",
  display: "swap",
})
const montserrat = Montserrat({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-montserrat",
  display: "swap",
})
const roboto = Roboto({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-roboto",
  display: "swap",
})
const openSans = Open_Sans({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-open-sans",
  display: "swap",
})
const lato = Lato({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-lato",
  display: "swap",
})
const nunito = Nunito({
  subsets: ["latin"],
  weight: ["400", "700", "900"],
  variable: "--font-nunito",
  display: "swap",
})
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-inter",
  display: "swap",
})

export const metadata: Metadata = {
  title: "Leka Product Catalogs",
  description: "Multi-brand product catalog by GO Corporation",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const fontVars = [
    poppins.variable,
    montserrat.variable,
    roboto.variable,
    openSans.variable,
    lato.variable,
    nunito.variable,
    inter.variable,
  ].join(" ")

  return (
    <html lang="en" className={fontVars}>
      <body>{children}</body>
    </html>
  )
}
