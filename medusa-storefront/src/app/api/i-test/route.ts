import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  return new Response(`hello at ${new Date().toISOString()}`, {
    status: 200,
    headers: { "content-type": "text/plain" },
  });
}
