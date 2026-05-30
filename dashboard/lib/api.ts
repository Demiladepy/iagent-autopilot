export const API_PREFIX = "/api/proxy";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_PREFIX}/${path.replace(/^\//, "")}`, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

/** Resolve WebSocket URL via server route so the API key stays server-side. */
export async function resolveWsUrl(): Promise<string> {
  try {
    const res = await fetch("/api/ws-url");
    if (res.ok) {
      const body = (await res.json()) as { url?: string };
      if (body.url) return body.url;
    }
  } catch {
    /* fallback below */
  }

  if (typeof window === "undefined") return "";
  const { protocol, hostname } = window.location;
  const wsProto = protocol === "https:" ? "wss:" : "ws:";
  return `${wsProto}//${hostname}:8000/ws`;
}
