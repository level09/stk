// Everything that names this server. Tool names and descriptions live in index.ts.
export const SITE = {
  name: "stk-docs-mcp",
  host: "mcp.stkit.dev",
  summary: "stk is a drift-proof Python framework for AI-built apps, published on PyPI as stkit. These are its docs, one section per heading.",
  instructions: "Read-only stk documentation from docs.stkit.dev. Use search_docs to find a topic, get_page to read a page or one of its sections, and get_command for a CLI command's usage and options. Answer from tool results. Inside a real app, its own state comes from uv run stk inspect context --json and uv run stk doctor.",
  resourceUri: "stk-docs-mcp://content",
};
