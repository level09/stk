"""
Evidence-grade collection record.
Archives cited sources to the Wayback Machine (link-rot defense) and builds a
methodology appendix so every report documents how, when, and with what tools
its sources were collected.
"""

import hashlib
import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from urllib.parse import unquote, urlparse

import httpx

log = logging.getLogger("evidence")

http = httpx.Client(timeout=8.0, follow_redirects=True)

_SKIP_DOMAINS = ("web.archive.org", "archive.ph", "r.jina.ai", "google.serper.dev")


def extract_cited_urls(markdown: str, limit: int = 10) -> list[str]:
    """Unique http(s) URLs cited in report prose, in order of appearance."""
    urls = []
    for m in re.finditer(r"\]\((https?://[^)\s]+)\)", markdown or ""):
        url = m.group(1)
        if any(d in url for d in _SKIP_DOMAINS) or url in urls:
            continue
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _archive_one(url: str) -> tuple[str, str]:
    """Return (url, snapshot_url). Existing snapshot wins; else request one."""
    try:
        r = http.get("https://archive.org/wayback/available", params={"url": url})
        snap = r.json().get("archived_snapshots", {}).get("closest", {})
        if snap.get("available") and snap.get("url"):
            return url, snap["url"].replace("http://", "https://", 1)
    except Exception:
        pass
    try:
        # Fire-and-forget SavePageNow; IA keeps archiving after we disconnect.
        http.get(f"https://web.archive.org/save/{url}", timeout=3.0)
    except Exception:
        pass
    return url, f"https://web.archive.org/web/{url}"


def archive_cited(report: str) -> dict[str, str]:
    """Map each cited URL to a Wayback snapshot (existing or freshly requested)."""
    urls = extract_cited_urls(report)
    if not urls:
        return {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        return dict(pool.map(_archive_one, urls))


def _archive_ledger(archives: dict[str, str]) -> str:
    rows = []
    for url, snapshot in archives.items():
        parsed = urlparse(url)
        domain = html.escape(parsed.netloc.removeprefix("www."), quote=True)
        path = unquote(parsed.path or "/")
        if parsed.query:
            path += "?" + unquote(parsed.query)
        if len(path) > 72:
            path = path[:69] + "..."
        safe_path = html.escape(path, quote=True)
        safe_url = html.escape(url, quote=True)
        safe_snapshot = html.escape(snapshot, quote=True)
        rows.append(
            '<div class="archive-row">'
            '<i class="ti ti-shield-check" aria-hidden="true"></i>'
            f'<span class="archive-source"><strong>{domain}</strong><small>{safe_path}</small></span>'
            '<span class="archive-actions">'
            f'<a href="{safe_url}" target="_blank" rel="noopener"><i class="ti ti-link" '
            'aria-hidden="true"></i>Original</a>'
            f'<a href="{safe_snapshot}" target="_blank" rel="noopener"><i class="ti ti-history" '
            'aria-hidden="true"></i>Snapshot</a>'
            "</span></div>"
        )
    return (
        '<section class="archive-section"><header><i class="ti ti-archive" aria-hidden="true"></i>'
        "<div><span>Link-rot protection</span><h3>Archived sources</h3></div></header>"
        f'<div class="archive-ledger">{"".join(rows)}</div></section>'
    )


def methodology_appendix(
    query: str,
    model: str,
    started_at: datetime,
    tool_log: list[dict],
    collected: dict,
    report_body: str,
    archives: dict[str, str],
) -> str:
    finished = datetime.now(UTC)
    sha = hashlib.sha256((report_body or "").encode()).hexdigest()
    fmt = "%Y-%m-%d %H:%M:%S"
    lines = [
        "---",
        "## Methodology & Collection Record",
        f"- Query: {query}",
        f"- Run: {started_at.strftime(fmt)} UTC to {finished.strftime(fmt)} UTC",
        f"- Orchestrator model: `{model}` via OpenRouter; web research: `perplexity/sonar-pro`; X search: `x-ai/grok-4.20`",
        f"- Collected: {len(collected.get('images', []))} images, {len(collected.get('videos', []))} videos, "
        f"{len(collected.get('news', []))} news items, {len(collected.get('docs', []))} documents",
        f"- Report body SHA-256 (pre-appendix): `{sha}`",
    ]
    if tool_log:
        lines += [
            "",
            f"<details><summary>Tool invocations ({len(tool_log)} total)</summary>",
            "",
        ]
        lines += [f"- `{t['ts']}` **{t['tool']}**: {t['label']}" for t in tool_log]
        lines += ["", "</details>"]
    if archives:
        lines += ["", _archive_ledger(archives)]
    return "\n".join(lines)
