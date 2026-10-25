// Builds content.md from the docs pages, so the server never drifts from docs.stkit.dev.
// Each "## " heading of a page becomes one section titled "Page: Heading"; CLI commands
// become sections titled by the command ("stk init").
import { readdirSync, readFileSync, writeFileSync } from "node:fs";

const docs = new URL("../docs/src/content/docs/", import.meta.url);
const base = "https://docs.stkit.dev";
// Same anchors Starlight generates for headings.
const slug = text => text.toLowerCase().replace(/<[^>]+>/g, "").replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "-");
const out = [
  "# stk documentation",
  "",
  "stk is a drift-proof Python framework for AI-built apps, published on PyPI as stkit (import stk, run stk). An app is a thin package made by `uvx --from stkit stk init <name>` that composes stk and never edits a framework file.",
  `Docs: ${base}. Full text: ${base}/llms-full.txt.`,
];
for (const file of readdirSync(docs).filter(f => f.endsWith(".md")).sort()) {
  const source = readFileSync(new URL(file, docs), "utf8");
  const [, front, body] = source.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  const title = front.match(/^title: *"?(.*?)"?$/m)[1];
  const page = `${base}/${file.replace(/\.md$/, "")}/`;
  const [intro, ...parts] = body.split(/^## /m);
  if (file === "cli.md") {
    for (const part of parts) for (const command of part.split(/^### /m).slice(1)) {
      const name = command.split("\n")[0].replaceAll("`", "").trim();
      out.push("", `## ${name}`, `URL: ${page}#${slug(name)}`, command.split("\n").slice(1).join("\n").trim());
    }
    continue;
  }
  if (intro.trim()) out.push("", `## ${title}: Overview`, `URL: ${page}`, intro.trim());
  for (const part of parts) {
    const heading = part.split("\n")[0].trim();
    out.push("", `## ${title}: ${heading}`, `URL: ${page}#${slug(heading)}`, part.split("\n").slice(1).join("\n").trim());
  }
}
writeFileSync(new URL("content.md", import.meta.url), out.join("\n") + "\n");
