import { McpServer } from "@modelcontextprotocol/server";
import { createMcpHandler } from "agents/mcp/server";
import { cap, content, getCommand, getPage, input, search } from "./content";
import { serve, type Env } from "./http";
import { SITE } from "./site";

const annotations = { readOnlyHint: true, openWorldHint: false };
const result = (text: string) => ({ content: [{ type: "text" as const, text: cap(text) }] });

export function createServer() {
  const server = new McpServer({ name: SITE.name, version: "1.0.0" }, { instructions: SITE.instructions });
  server.registerTool("search_docs", {
    description: "Find up to eight keyword matches across the stk docs and CLI reference, with the lines that match and their docs URLs.",
    inputSchema: { query: input }, annotations,
  }, async ({ query }) => result(search(query)));
  server.registerTool("get_page", {
    description: "Read a docs section by its full title (\"Models: Migrations\"). A page title (\"Models\") lists that page's sections; anything else lists every page.",
    inputSchema: { title: input }, annotations,
  }, async ({ title }) => result(getPage(title)));
  server.registerTool("get_command", {
    description: "Read one stk CLI command's usage and options, e.g. \"db upgrade\" or \"stk smoke\". Unknown names list every command.",
    inputSchema: { name: input }, annotations,
  }, async ({ name }) => result(getCommand(name)));
  server.registerResource("content.md", SITE.resourceUri, { mimeType: "text/markdown" }, async uri => ({
    contents: [{ uri: uri.href, mimeType: "text/markdown", text: content }],
  }));
  return server;
}
const handler = createMcpHandler(createServer, {
  allowedHostnames: [SITE.host, "localhost", "127.0.0.1"],
  allowedOriginHostnames: "*",
});
export default {
  fetch(request, env, ctx) { return serve(request, env, ctx, handler); },
} satisfies ExportedHandler<Env>;
