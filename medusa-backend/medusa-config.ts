import { defineConfig, loadEnv } from "@medusajs/framework/utils"

loadEnv(process.env.NODE_ENV || "development", process.cwd())

const IS_PROD = process.env.NODE_ENV === "production"

// Validate required env vars in production
if (IS_PROD) {
  const required = ["DATABASE_URL", "REDIS_URL", "COOKIE_SECRET", "JWT_SECRET"]
  for (const key of required) {
    if (!process.env[key]) {
      throw new Error(`Missing required environment variable: ${key}`)
    }
  }
}

// File storage: GCS in production, local in development
const fileModule = IS_PROD && process.env.GCS_BUCKET
  ? {
      resolve: "@medusajs/file-s3",
      options: {
        // Use S3-compatible API for GCS
        file_url: `https://storage.googleapis.com/${process.env.GCS_BUCKET}`,
        access_key_id: process.env.GCS_ACCESS_KEY || "",
        secret_access_key: process.env.GCS_SECRET_KEY || "",
        region: process.env.GCS_REGION || "asia-southeast1",
        bucket: process.env.GCS_BUCKET,
        prefix: process.env.GCS_PREFIX || "medusa-uploads",
        endpoint: "https://storage.googleapis.com",
      },
    }
  : {
      resolve: "@medusajs/file-local",
      options: {
        upload_dir: "uploads",
      },
    }

export default defineConfig({
  projectConfig: {
    databaseUrl: process.env.DATABASE_URL,
    redisUrl: process.env.REDIS_URL,
    http: {
      storeCors: process.env.STORE_CORS || (IS_PROD ? "" : "http://localhost:3000"),
      adminCors: process.env.ADMIN_CORS || (IS_PROD ? "" : "http://localhost:5173"),
      authCors: process.env.AUTH_CORS || (IS_PROD ? "" : "http://localhost:3000,http://localhost:5173"),
    },
  },
  admin: {
    backendUrl: process.env.MEDUSA_BACKEND_URL || (IS_PROD ? "" : "http://localhost:9000"),
  },
  modules: [fileModule],
})
