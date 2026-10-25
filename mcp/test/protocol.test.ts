import { env, createExecutionContext } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import worker from "../src/index";
import { content, sections } from "../src/content";
import { SITE } from "../src/site";

async function rpc(method: string, params: Record<string, unknown> = {}) {
  const response = await worker.fetch(new Request(`https://${SITE.host}/mcp`, {
    method: "POST",
    headers: { Host: SITE.host, "Content-Type": "application/json", Accept: "application/json, text/event-stream", "CF-Connecting-IP": "192.0.2.50" },
    body: JSON.stringify({ jsonrpc: "2.0", id: "x".repeat(80), method, params }),
  }), env as Parameters<typeof worker.fetch>[1], createExecutionContext());
  expect(response.status).toBe(200);
  const text = await response.text();
  return JSON.parse(response.headers.get("Content-Type")?.includes("text/event-stream")
    ? text.split("\n").find(line => line.startsWith("data: "))!.slice(6)
    : text);
}
const first = sections[0];
describe("MCP protocol", () => {
  it("has content to serve", () => expect(sections.length).toBeGreaterThan(0));
  it("publishes exactly three read-only tools", async () => {
    const { result } = await rpc("tools/list");
    expect(result.tools.map((t: any) => t.name).sort()).toEqual(["get_command", "get_page", "search_docs"]);
    for (const tool of result.tools) expect(tool.annotations).toMatchObject({ readOnlyHint: true, openWorldHint: false });
  });
  it.each([
    ["search_docs", { query: "selectin" }, "https://docs.stkit.dev/models/"],
    ["search_docs", { query: "zz-no-such-term-zz" }, "no match"],
    ["get_page", { title: "Models and Migrations" }, "Models and Migrations: "],
    ["get_page", { title: "zz-unknown-zz" }, "Quick Start"],
    ["get_page", { title: first.title }, first.title],
    ["get_command", { name: "db upgrade" }, "stk db upgrade"],
    ["get_command", { name: "uv run stk smoke" }, "stk smoke"],
    ["get_command", { name: "zz" }, "stk init"],
  ])("calls %s with %j", async (name, args, expected) => {
    const response = await rpc("tools/call", { name, arguments: args });
    expect(response.result.isError).not.toBe(true);
    expect(response.result.content[0].text).toContain(expected);
    expect(new TextEncoder().encode(JSON.stringify(response)).length).toBeLessThanOrEqual(4096);
  });
  it.each(["", "x".repeat(500), "a\nb", 42])("rejects invalid arguments %j", async query => {
    const response = await rpc("tools/call", { name: "search_docs", arguments: { query } });
    expect(response.error || response.result?.isError).toBeTruthy();
  });
  it("serves the complete content as one resource", async () => {
    const { result } = await rpc("resources/read", { uri: SITE.resourceUri });
    expect(result.contents[0].text).toBe(content);
  });
  it("advertises no write-oriented capabilities", async () => {
    const { result } = await rpc("initialize", { protocolVersion: "2025-11-25", capabilities: {}, clientInfo: { name: "test", version: "1.0" } });
    expect(result.serverInfo.name).toBe(SITE.name);
    expect(result.instructions).toBe(SITE.instructions);
    for (const key of ["prompts", "sampling", "elicitation"]) expect(result.capabilities).not.toHaveProperty(key);
  });
});
