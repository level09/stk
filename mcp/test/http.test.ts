import { expect, it, vi } from "vitest";
import { serve } from "../src/http";
const ctx = { waitUntil() {}, passThroughOnException() {} } as ExecutionContext;
const env = (success = true) => ({ RATE_LIMITER: { limit: vi.fn(async () => ({ success })) } });
const handler = vi.fn(async () => new Response("ok"));
it("limits requests per IP", async () => {
  const bindings = env(false);
  const response = await serve(new Request("https://mcp.stkit.dev/mcp", { headers: { "CF-Connecting-IP": "192.0.2.1" } }), bindings, ctx, handler);
  expect(response.status).toBe(429);
  expect(bindings.RATE_LIMITER.limit).toHaveBeenCalledWith({ key: "192.0.2.1" });
});
it.each([true, false])("rejects oversized bodies with declared length %s", async declared => {
  const response = await serve(new Request("https://mcp.stkit.dev/mcp", { method: "POST", body: "x".repeat(16385), headers: declared ? { "Content-Length": "16385" } : {} }), env(), ctx, handler);
  expect(response.status).toBe(413);
});
it("allows cross-origin preflight without credentials", async () => {
  const response = await serve(new Request("https://mcp.stkit.dev/mcp", { method: "OPTIONS", headers: { Origin: "https://client.example" } }), env(), ctx, handler);
  expect(response.status).toBe(204);
  expect(response.headers.get("Access-Control-Allow-Origin")).toBe("*");
  expect(response.headers.has("Access-Control-Allow-Credentials")).toBe(false);
});
it("rejects opaque origins", async () => expect((await serve(new Request("https://mcp.stkit.dev/mcp", { headers: { Origin: "null" } }), env(), ctx, handler)).status).toBe(403));
it("returns the client setup page", async () => expect(await (await serve(new Request("https://mcp.stkit.dev/"), env(), ctx, handler)).text()).toContain("https://mcp.stkit.dev/mcp"));
it("rejects IDs that could exceed the response cap", async () => {
  const response = await serve(new Request("https://mcp.stkit.dev/mcp", {
    method: "POST", body: JSON.stringify({ jsonrpc: "2.0", id: "x".repeat(15000), method: "tools/call" }),
  }), env(), ctx, handler);
  expect(response.status).toBe(400);
  expect((await response.text()).length).toBeLessThan(4096);
});
