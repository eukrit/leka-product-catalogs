/**
 * Image proxy: streams private GCS objects from `gs://ai-agents-go-vendors`
 * to anonymous storefront visitors using Cloud Run's runtime SA via ADC.
 *
 * URL shape: /api/i/<vendor>/<...path>
 * Maps to:   gs://ai-agents-go-vendors/<vendor>/<...path>
 *
 * Auth: GCE/Cloud Run metadata server -> bearer token cached until ~5 min before
 *       expiry. Local dev needs `gcloud auth application-default login` to source
 *       a token from the well-known ADC file (not handled here — Cloud Run only).
 */

import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";
export const revalidate = 0;

const BUCKET = process.env.IMAGE_PROXY_BUCKET || "ai-agents-go-vendors";
const METADATA_TOKEN_URL =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token";

let cachedToken: { value: string; expiresAt: number } | null = null;

async function getAccessToken(): Promise<string> {
  const now = Date.now();
  if (cachedToken && cachedToken.expiresAt > now + 60_000) {
    return cachedToken.value;
  }
  const r = await fetch(METADATA_TOKEN_URL, {
    headers: { "Metadata-Flavor": "Google" },
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`metadata token fetch failed: ${r.status}`);
  }
  const body = (await r.json()) as { access_token: string; expires_in: number };
  cachedToken = {
    value: body.access_token,
    expiresAt: now + (body.expires_in - 300) * 1000,
  };
  return cachedToken.value;
}

const PREFIX = "/api/i/";

export async function GET(req: NextRequest) {
  // Preserve the URL path as-sent. Decoding via params and re-encoding loses
  // distinctions like literal `%20` (filename has %, 2, 0 chars) vs. encoded
  // space (filename has a space). 4soft's catalog has literal `%20` in object
  // names, so we must pass the raw path through to GCS.
  const url = new URL(req.url);
  const idx = url.pathname.indexOf(PREFIX);
  if (idx < 0) {
    return new Response("not found", { status: 404 });
  }
  const objectPath = url.pathname.slice(idx + PREFIX.length);
  if (!objectPath) {
    return new Response("not found", { status: 404 });
  }
  const gcsUrl = `https://storage.googleapis.com/${BUCKET}/${objectPath}`;

  let token: string;
  try {
    token = await getAccessToken();
  } catch (e) {
    console.error("[image-proxy] token error", e);
    return new Response("upstream auth failed", { status: 502 });
  }

  const upstream = await fetch(gcsUrl, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  if (!upstream.ok) {
    if (upstream.status === 404) {
      return new Response("not found", { status: 404 });
    }
    console.error(
      "[image-proxy] upstream",
      upstream.status,
      decodeURIComponent(objectPath),
    );
    return new Response("upstream error", { status: 502 });
  }

  const contentType =
    upstream.headers.get("content-type") || "application/octet-stream";
  const contentLength = upstream.headers.get("content-length");
  const headers = new Headers({
    "content-type": contentType,
    "cache-control": "public, max-age=86400, immutable",
  });
  if (contentLength) headers.set("content-length", contentLength);

  return new Response(upstream.body, { status: 200, headers });
}
