import { z } from "zod";
import content from "../content.md";

// content.md: a preamble, then one entry per "## Title" section. An optional
// "URL: https://..." line inside a section is returned with every match from it.
export { content };
export const input = z.string().regex(/^[\x20-\x7e]+$/, "Use 1 to 80 printable characters.").trim().min(1).max(80);
const [preamble, ...blocks] = content.split(/^## /m);
export const sections = blocks.map(block => ({
  title: block.split("\n")[0].trim(),
  url: block.match(/^URL: *(.*)$/m)?.[1] ?? "",
  text: `## ${block.trim()}`,
}));
const encoder = new TextEncoder();
// MCP clients truncate or reject large tool results; 4000 bytes leaves room for the JSON-RPC envelope.
export function cap(text: string) {
  let result = "";
  for (const character of text) {
    if (encoder.encode(result + character).length > 4000) break;
    result += character;
  }
  return result;
}
export function search(query: unknown) {
  const keyword = input.parse(query).toLowerCase();
  const matches = sections.filter(s => s.text.toLowerCase().includes(keyword)).slice(0, 8);
  if (!matches.length) return "no match";
  const results: string[] = [];
  for (const s of matches) {
    const lines = s.text.split("\n").slice(1).filter(line => line.toLowerCase().includes(keyword) && !line.startsWith("URL:"));
    const result = [`## ${s.title}`, ...(s.url ? [`URL: ${s.url}`] : []), ...lines].join("\n");
    if (encoder.encode([...results, result].join("\n\n")).length > 4000) break;
    results.push(result);
  }
  return results.join("\n\n");
}
const pages = [...new Set(sections.filter(s => !s.title.startsWith("stk ")).map(s => s.title.split(": ")[0]))];
export function getPage(title: unknown) {
  const keyword = input.parse(title).toLowerCase();
  const match = sections.find(s => s.title.toLowerCase() === keyword);
  if (match) return cap(match.text);
  const parts = sections.filter(s => s.title.toLowerCase().split(": ")[0] === keyword).map(s => `- ${s.title}`);
  if (parts.length) return cap(`Sections of this page; read one by its full title:\n${parts.join("\n")}`);
  return cap(`${preamble.trim()}\n\nPages; read one by title to list its sections:\n${pages.map(p => `- ${p}`).join("\n")}`);
}
export function getCommand(name: unknown) {
  const command = `stk ${input.parse(name).toLowerCase().replace(/^(uv run )?stk /, "")}`;
  const match = sections.find(s => s.title === command);
  return cap(match ? match.text : `Unknown command. Commands:\n${sections.filter(s => s.title.startsWith("stk ")).map(s => s.title).join("\n")}`);
}
