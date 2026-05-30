import { NextRequest, NextResponse } from "next/server";

const RUNTIME_URL = process.env.RUNTIME_API_URL || "http://127.0.0.1:8000";
const API_KEY = process.env.SENTINEL_API_KEY || "";

function runtimeHeaders(req: NextRequest): Headers {
  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  if (API_KEY) headers.set("X-Sentinel-API-Key", API_KEY);
  return headers;
}

async function proxyRequest(req: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join("/");
  const url = new URL(`${RUNTIME_URL}/${path}`);
  req.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value);
  });

  const init: RequestInit = {
    method: req.method,
    headers: runtimeHeaders(req),
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
  }

  const res = await fetch(url.toString(), init);
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json" },
  });
}

export async function GET(
  req: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(req, params.path);
}

export async function POST(
  req: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(req, params.path);
}

export async function PUT(
  req: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(req, params.path);
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(req, params.path);
}
