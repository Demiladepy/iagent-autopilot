import { NextResponse } from "next/server";

/** Returns WebSocket URL with server-side API key (never exposed to the client bundle). */
export async function GET() {
  const runtime = process.env.RUNTIME_API_URL || "http://127.0.0.1:8000";
  const apiKey = process.env.SENTINEL_API_KEY || "";

  let url: URL;
  try {
    url = new URL(runtime);
  } catch {
    url = new URL("http://127.0.0.1:8000");
  }

  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws";
  if (apiKey) {
    url.searchParams.set("api_key", apiKey);
  }

  return NextResponse.json({ url: url.toString() });
}
