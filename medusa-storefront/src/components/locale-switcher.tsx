"use client"

import { useState, useEffect } from "react"
import { LOCALES, getLocale, setLocale, type Locale } from "@/lib/i18n"

export function LocaleSwitcher() {
  const [current, setCurrent] = useState<Locale>("en")

  useEffect(() => {
    setCurrent(getLocale())
  }, [])

  function handleChange(locale: Locale) {
    setLocale(locale)
    setCurrent(locale)
    window.location.reload()
  }

  return (
    <div className="flex items-center gap-1">
      {LOCALES.map((loc) => (
        <button
          key={loc.code}
          onClick={() => handleChange(loc.code)}
          className={`text-sm px-2 py-1 rounded transition-colors ${
            current === loc.code
              ? "bg-leka-purple text-white"
              : "text-gray-400 hover:text-leka-purple"
          }`}
          title={loc.label}
        >
          {loc.flag}
        </button>
      ))}
    </div>
  )
}
