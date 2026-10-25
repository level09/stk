import { SITE } from "./site";

export interface Env {
  RATE_LIMITER: RateLimit;
}
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Accept, MCP-Protocol-Version, MCP-Session-Id, Last-Event-ID",
  "Access-Control-Expose-Headers": "MCP-Protocol-Version, MCP-Session-Id",
};
export async function serve(request: Request, env: Env, ctx: ExecutionContext, handler: (request: Request, env: Env, ctx: ExecutionContext) => Promise<Response>) {
  const respond = (text: string, status: number) => new Response(text, { status, headers: { ...cors, "Content-Type": "text/plain; charset=utf-8" } });
  if (!(await env.RATE_LIMITER.limit({ key: request.headers.get("CF-Connecting-IP") ?? "local" })).success) {
    return new Response("Too many requests", { status: 429, headers: { ...cors, "Retry-After": "60" } });
  }
  const origin = request.headers.get("Origin");
  if (origin) {
    try {
      if (!["http:", "https:"].includes(new URL(origin).protocol)) return respond("Invalid origin", 403);
    } catch { return respond("Invalid origin", 403); }
  }
  if (!["GET", "POST", "OPTIONS"].includes(request.method)) return respond("Method not allowed", 405);
  const path = new URL(request.url).pathname;
  if (path !== "/" && path !== "/mcp") return respond("Not found", 404);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (path === "/") return request.method === "GET"
    ? respond(`${SITE.summary} Add this Streamable HTTP endpoint to your MCP client: https://${SITE.host}/mcp`, 200)
    : respond("Method not allowed", 405);
  if (request.method === "POST") {
    if (Number(request.headers.get("Content-Length")) > 16384) return respond("Request body exceeds 16 KB", 413);
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 16384) { await reader.cancel(); return respond("Request body exceeds 16 KB", 413); }
        chunks.push(value);
      }
    }
    const body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
    let message: unknown;
    try { message = JSON.parse(new TextDecoder().decode(body)); }
    catch { return respond("Invalid JSON", 400); }
    if (typeof message !== "object" || message === null || Array.isArray(message)) return respond("Use one JSON-RPC request", 400);
    const id = (message as { id?: unknown }).id;
    if (typeof id === "string" && (id.length > 80 || /[^\x20-\x7e]/.test(id))) return respond("Request ID must contain at most 80 printable characters", 400);
    request = new Request(request, { body });
  }
  const response = await handler(request, env, ctx);
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries(cors)) headers.set(key, value);
  headers.delete("Access-Control-Allow-Credentials");
  return new Response(response.body, { status: response.status, headers });
}
