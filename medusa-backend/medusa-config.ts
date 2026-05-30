import { defineConfig, loadEnv } from "@medusajs/framework/utils"

loadEnv(process.env.NODE_ENV || "development", process.cwd())

const IS_PROD = process.env.NODE_ENV === "production"

if (IS_PROD) {
  const required = ["DATABASE_URL", "COOKIE_SECRET", "JWT_SECRET"]
  for (const key of required) {
    if (!process.env[key]) {
      throw new Error(`Missing required environment variable: ${key}`)
    }
  }
}

// Customer-facing social login (Google) auto-registers when all three vars
// are set. On dev machines without OAuth creds the auth module still boots
// with just the default emailpass provider — the backend never crashes for
// missing OAuth config.
const googleConfigured =
  !!process.env.GOOGLE_CLIENT_ID &&
  !!process.env.GOOGLE_CLIENT_SECRET &&
  !!process.env.GOOGLE_CALLBACK_URL

const authProviders: Array<Record<string, any>> = [
  {
    resolve: "@medusajs/medusa/auth-emailpass",
    id: "emailpass",
    options: {},
  },
]

if (googleConfigured) {
  authProviders.push({
    resolve: "@medusajs/medusa/auth-google",
    id: "google",
    options: {
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
      callbackUrl: process.env.GOOGLE_CALLBACK_URL,
    },
  })
}

export default defineConfig({
  projectConfig: {
    databaseUrl: process.env.DATABASE_URL || "postgres://localhost:5432/medusa",
    redisUrl: process.env.REDIS_URL,
    http: {
      storeCors: process.env.STORE_CORS || "http://localhost:3000",
      adminCors: process.env.ADMIN_CORS || "http://localhost:5173",
      authCors: process.env.AUTH_CORS || "http://localhost:3000,http://localhost:5173",
    },
  },
  admin: {
    backendUrl: process.env.MEDUSA_BACKEND_URL || "http://localhost:9000",
    disable: process.env.DISABLE_ADMIN === "true",
  },
  modules: [
    {
      resolve: "@medusajs/medusa/auth",
      options: {
        providers: authProviders,
      },
    },
    {
      resolve: "./src/modules/brand",
    },
  ],
})
