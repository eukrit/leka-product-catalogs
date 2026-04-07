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
  },
  modules: [
    {
      resolve: IS_PROD && process.env.GCS_BUCKET
        ? "@medusajs/file-s3"
        : "@medusajs/file-local",
      options: IS_PROD && process.env.GCS_BUCKET
        ? {
            file_url: `https://storage.googleapis.com/${process.env.GCS_BUCKET}`,
            access_key_id: process.env.GCS_ACCESS_KEY || "",
            secret_access_key: process.env.GCS_SECRET_KEY || "",
            region: process.env.GCS_REGION || "asia-southeast1",
            bucket: process.env.GCS_BUCKET,
            prefix: process.env.GCS_PREFIX || "medusa-uploads",
            endpoint: "https://storage.googleapis.com",
          }
        : { upload_dir: "uploads" },
    },
  ],
})
