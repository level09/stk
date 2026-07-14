"""
Multi-source research agent.
Uses OpenRouter (Gemini Flash default) as orchestrator with multiple research sources:
- Perplexity Sonar (via OpenRouter) for AI-powered web research
- Serper (Google Search API) for image, video, news, and document search
- Jina Reader for page scraping
- youtube-transcript-api for YouTube transcripts
Yields structured events for the UI via websocket.
"""

import html
import json
import logging
import os
import re
import sys
import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from urllib.parse import quote, urlparse

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from . import evidence, knowledge

load_dotenv()

log = logging.getLogger("agent")

MODEL = os.environ.get("MODEL", "google/gemini-3.1-flash-lite")
LLM_TIMEOUT = 180.0
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
JINA_PREFIX = "https://r.jina.ai/"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_research",
            "description": (
                "Research a topic using AI-powered web search. Returns a detailed answer "
                "with citations and source URLs. This is your PRIMARY research tool. "
                "Use it for any factual question, background research, or investigation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The research question or topic to investigate",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_images",
            "description": (
                "Search for images related to a query. Returns URLs, titles, and thumbnails. "
                "Use for finding photos, satellite imagery, visual evidence, or illustrations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Image search query"},
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_videos",
            "description": (
                "Search YouTube for videos related to a query. Returns YouTube URLs, titles, durations, "
                "and thumbnails. Social-platform clips belong to search_social, not this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Video search query"},
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": (
                "Search for recent news articles. Returns URLs, titles, dates, and sources. "
                "Use for finding current coverage, breaking news, or recent developments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "News search query"},
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "Search for PDF documents and reports. Returns URLs, titles, and sources. "
                "Use for finding official reports, legal documents, academic papers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Document search query"},
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_page",
            "description": (
                "Read the full content of a web page as clean markdown. "
                "Use to get detailed content from a specific URL found via research or search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to read"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_video_transcript",
            "description": (
                "Get the transcript of a YouTube video. "
                "Use to extract spoken content from YouTube videos found via search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "youtube_url": {
                        "type": "string",
                        "description": "YouTube video URL or video ID",
                    },
                },
                "required": ["youtube_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_video_url",
            "description": (
                "Build an evidence-oriented dossier for a YouTube video: metadata, "
                "timestamped transcript, thumbnails, and verification pivots. "
                "Use this for videos that may contain eyewitness footage, testimony, "
                "news footage, or other human-rights documentation value."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "youtube_url": {
                        "type": "string",
                        "description": "YouTube video URL or video ID",
                    },
                    "title": {
                        "type": "string",
                        "description": "Known title, if already available",
                    },
                    "source": {
                        "type": "string",
                        "description": "Known source/channel, if already available",
                    },
                    "date": {
                        "type": "string",
                        "description": "Known publish date, if already available",
                    },
                    "duration": {
                        "type": "string",
                        "description": "Known duration, if already available",
                    },
                    "thumbnail": {
                        "type": "string",
                        "description": "Known thumbnail URL, if already available",
                    },
                },
                "required": ["youtube_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_social",
            "description": (
                "Search social media platforms. Use when the topic involves public discourse, "
                "eyewitness accounts, activist posts, or community discussions. "
                "Supported platforms: twitter (uses AI-powered X search), facebook, instagram, "
                "reddit, telegram. Use this when social media perspectives would add value."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "platform": {
                        "type": "string",
                        "description": "Platform to search: twitter, facebook, instagram, reddit, telegram",
                        "enum": [
                            "twitter",
                            "facebook",
                            "instagram",
                            "reddit",
                            "telegram",
                        ],
                    },
                },
                "required": ["query", "platform"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": (
                "Record a reflection between search rounds: what you have learned so far, "
                "what is missing or contradictory, and what to search next. "
                "Use this before launching more searches to avoid redundant queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reflection": {
                        "type": "string",
                        "description": "Your reflection on progress and next steps",
                    },
                },
                "required": ["reflection"],
            },
        },
    },
]

http = httpx.Client(timeout=30.0)


def _sonar_research(query: str) -> str:
    """Use Perplexity Sonar via OpenRouter for AI-powered web research."""
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
        timeout=LLM_TIMEOUT,
    )
    response = client.chat.completions.create(
        model="perplexity/sonar-pro",
        messages=[
            {
                "role": "system",
                "content": "You are a research assistant. Provide detailed, factual answers with source URLs.",
            },
            {"role": "user", "content": query},
        ],
        max_tokens=4096,
    )
    content = response.choices[0].message.content or ""
    return json.dumps({"answer": content}, indent=2)


SERPER_ENDPOINTS = {
    "images": "https://google.serper.dev/images",
    "videos": "https://google.serper.dev/videos",
    "news": "https://google.serper.dev/news",
    "search": "https://google.serper.dev/search",
}


def _serper_search(query: str, category: str, limit: int = 5) -> str:
    """Query Serper (Google Search API) for a specific category."""
    endpoint = SERPER_ENDPOINTS.get(category, SERPER_ENDPOINTS["search"])
    payload = {"q": query, "num": limit}
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    r = http.post(endpoint, json=payload, headers=headers)
    r.raise_for_status()
    data = r.json()

    if category == "images":
        items = data.get("images", [])[:limit]
        results = [
            {
                "url": item.get("imageUrl", ""),
                "title": item.get("title", ""),
                "source": item.get("source", "") or item.get("domain", ""),
                "thumbnail": item.get("thumbnailUrl", "") or item.get("imageUrl", ""),
            }
            for item in items
        ]
    elif category == "videos":
        items = data.get("videos", [])[:limit]
        results = [
            {
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "duration": item.get("duration", ""),
                "thumbnail": item.get("imageUrl", ""),
                "source": item.get("source", ""),
                "date": item.get("date", ""),
            }
            for item in items
        ]
    elif category == "news":
        items = data.get("news", [])[:limit]
        results = [
            {
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "date": item.get("date", ""),
                "source": item.get("source", ""),
                "thumbnail": item.get("imageUrl", ""),
            }
            for item in items
        ]
    else:  # general/documents
        items = data.get("organic", [])[:limit]
        results = [
            {
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "source": item.get("domain", "") or item.get("source", ""),
            }
            for item in items
        ]

    return json.dumps(results, indent=2)


def _video_search_queries(query: str) -> list[str]:
    """Return deterministic video queries biased toward evidence-rich YouTube results."""
    base = query.strip()
    return [
        base,
        f"{base} youtube eyewitness footage testimony",
        f"{base} site:youtube.com",
    ]


def _dedupe_results(items: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for item in items:
        url = item.get("url", "")
        key = url or item.get("title", "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _filter_youtube_results(items: list[dict]) -> list[dict]:
    """Keep the video lane distinct from social-platform collection."""
    allowed_hosts = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
    return [
        item
        for item in items
        if urlparse(item.get("url", "")).hostname in allowed_hosts
    ]


def _search_videos(query: str, limit: int = 5) -> str:
    """Search videos and enrich likely YouTube results with evidence dossiers."""
    raw_results = []
    for search_query in _video_search_queries(query):
        raw_results.extend(json.loads(_serper_search(search_query, "videos", limit)))
    results = _filter_youtube_results(_dedupe_results(raw_results))[:limit]
    enriched = []
    dossier_count = 0
    for item in results:
        if dossier_count < 3 and _extract_video_id(item.get("url", "")) != item.get(
            "url", ""
        ):
            dossier = _analyze_video_url(
                item.get("url", ""),
                title=item.get("title", ""),
                source=item.get("source", ""),
                date=item.get("date", ""),
                duration=item.get("duration", ""),
                thumbnail=item.get("thumbnail", ""),
            )
            item["dossier"] = dossier
            dossier_count += 1
        enriched.append(item)
    return json.dumps(enriched, indent=2)


def _emit_video_results(
    parsed: list[dict],
    collected: dict,
    events: list[dict],
    tool_name: str = "search_videos",
):
    collected["videos"].extend(parsed)
    events.append(event("tool_result", tool=tool_name, count=len(parsed)))
    if parsed:
        events.append(event("media", kind="videos", items=parsed[:6]))
        dossiers = [item["dossier"] for item in parsed if item.get("dossier")]
        if dossiers:
            events.append(event("video_dossiers", items=dossiers[:3]))


def _prefetch_video_evidence(
    query: str, collected: dict, disabled_tools: set
) -> Generator[dict, None, None]:
    if "search_videos" in disabled_tools:
        return
    yield event(
        "tool_call",
        tool="search_videos",
        args={"query": query, "limit": 8},
        label=f"(video evidence) {query[:80]}",
    )
    result = execute_tool("search_videos", {"query": query, "limit": 8})
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        yield event(
            "tool_error",
            tool="search_videos",
            error="Video search returned invalid JSON",
        )
        return
    if isinstance(parsed, list):
        evs = []
        _emit_video_results(parsed, collected, evs)
        yield from evs
    elif isinstance(parsed, dict) and parsed.get("error"):
        yield event("tool_error", tool="search_videos", error=parsed["error"])


def _prefetched_video_context(videos: list[dict]) -> str:
    lines = []
    for video in videos[:5]:
        dossier = video.get("dossier") or {}
        transcript = dossier.get("transcript", "")
        excerpt = "\n".join(transcript.splitlines()[:8])
        lines.append(
            "\n".join(
                filter(
                    None,
                    [
                        f"- Title: {video.get('title', '')}",
                        f"  URL: {video.get('url', '')}",
                        f"  Source: {video.get('source', '')}",
                        f"  Date: {video.get('date', '')}",
                        f"  Transcript excerpt:\n{excerpt}" if excerpt else "",
                    ],
                )
            )
        )
    return "\n\n".join(lines)


def _llm_tools_after_prefetch(active_tools: list[dict], collected: dict) -> list[dict]:
    if not collected.get("videos"):
        return active_tools
    return [
        tool for tool in active_tools if tool["function"]["name"] != "search_videos"
    ]


def _jina_read(url: str) -> str:
    """Read a page via Jina Reader."""
    r = http.get(f"{JINA_PREFIX}{url}", headers={"Accept": "text/markdown"})
    r.raise_for_status()
    content = r.text[:12000]
    return json.dumps({"url": url, "content": content}, indent=2)


def _extract_video_id(url_or_id: str) -> str:
    """Extract YouTube video ID from URL or return as-is if already an ID."""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return url_or_id


def _youtube_transcript_entries(youtube_url: str) -> list[dict]:
    """Get timestamped transcript entries from a YouTube video.

    YouTube blocks datacenter IPs; set WEBSHARE_PROXY_USERNAME/PASSWORD
    (residential rotating proxy) when deploying on a VPS.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = _extract_video_id(youtube_url)
    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        return _normalize_transcript_entries(
            YouTubeTranscriptApi.get_transcript(video_id)
        )
    proxy_config = None
    user = os.environ.get("WEBSHARE_PROXY_USERNAME")
    password = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    if user and password:
        from youtube_transcript_api.proxies import WebshareProxyConfig

        proxy_config = WebshareProxyConfig(proxy_username=user, proxy_password=password)
    return _normalize_transcript_entries(
        YouTubeTranscriptApi(proxy_config=proxy_config).fetch(video_id)
    )


def _normalize_transcript_entries(entries) -> list[dict]:
    normalized = []
    for entry in entries:
        if isinstance(entry, dict):
            text = entry.get("text", "")
            start = entry.get("start", 0)
            duration = entry.get("duration", 0)
        else:
            text = getattr(entry, "text", "")
            start = getattr(entry, "start", 0)
            duration = getattr(entry, "duration", 0)
        normalized.append({"text": text, "start": start, "duration": duration})
    return normalized


def _format_seconds(seconds: float) -> str:
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _timestamped_transcript(entries: list[dict], limit: int = 10000) -> str:
    lines = []
    for entry in entries:
        text = " ".join(str(entry.get("text", "")).split())
        if not text:
            continue
        lines.append(f"[{_format_seconds(entry.get('start', 0))}] {text}")
    transcript = "\n".join(lines)
    if len(transcript) > limit:
        transcript = transcript[:limit] + "\n... [truncated]"
    return transcript


def _youtube_thumbnail_urls(video_id: str, fallback: str = "") -> list[str]:
    urls = [
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
    ]
    if fallback and fallback not in urls:
        urls.insert(0, fallback)
    return urls


def _build_video_dossier(
    video: dict,
    transcript_entries: list[dict] | None = None,
    transcript_error: str = "",
) -> dict:
    """Build a compact evidence-oriented dossier for a video result."""
    url = video.get("url") or video.get("youtube_url", "")
    video_id = _extract_video_id(url)
    thumbnail = video.get("thumbnail", "")
    thumbnail_urls = (
        _youtube_thumbnail_urls(video_id, thumbnail)
        if len(video_id) == 11
        else ([thumbnail] if thumbnail else [])
    )
    primary_thumb = thumbnail_urls[0] if thumbnail_urls else ""
    transcript_entries = transcript_entries or []

    return {
        "video_id": video_id,
        "url": url,
        "title": video.get("title", ""),
        "source": video.get("source", ""),
        "date": video.get("date", ""),
        "duration": video.get("duration", ""),
        "captured_at": datetime.now(UTC).isoformat(),
        "transcript": _timestamped_transcript(transcript_entries)
        if transcript_entries
        else "",
        "transcript_error": transcript_error,
        "verification_pivots": {
            "thumbnails": thumbnail_urls,
            "reverse_image_search": f"https://lens.google.com/uploadbyurl?url={quote(primary_thumb, safe='')}"
            if primary_thumb
            else "",
            "youtube_data_viewer": f"https://www.ytdataviewer.com/video/{video_id}"
            if len(video_id) == 11
            else "",
        },
        "evidence": {
            "platform": "youtube" if len(video_id) == 11 else "video",
            "capture_method": "metadata_and_transcript",
            "source_url": url,
            "original_title": video.get("title", ""),
            "original_source": video.get("source", ""),
        },
    }


def _analyze_video_url(
    youtube_url: str,
    title: str = "",
    source: str = "",
    date: str = "",
    duration: str = "",
    thumbnail: str = "",
) -> dict:
    video = {
        "url": youtube_url,
        "title": title,
        "source": source,
        "date": date,
        "duration": duration,
        "thumbnail": thumbnail,
    }
    try:
        r = http.get(
            "https://www.youtube.com/oembed",
            params={"url": youtube_url, "format": "json"},
        )
        if r.status_code == 200:
            meta = r.json()
            video["title"] = video["title"] or meta.get("title", "")
            video["source"] = video["source"] or meta.get("author_name", "")
            video["thumbnail"] = video["thumbnail"] or meta.get("thumbnail_url", "")
    except Exception:
        pass

    try:
        transcript = _youtube_transcript_entries(youtube_url)
        return _build_video_dossier(video, transcript)
    except Exception as e:
        return _build_video_dossier(video, transcript_error=str(e))


def _youtube_transcript(youtube_url: str) -> str:
    """Get transcript from a YouTube video."""
    video_id = _extract_video_id(youtube_url)
    transcript = _youtube_transcript_entries(youtube_url)
    full_text = _timestamped_transcript(transcript)
    # Truncate if very long
    if len(full_text) > 10000:
        full_text = full_text[:10000] + "... [truncated]"
    return json.dumps({"video_id": video_id, "transcript": full_text}, indent=2)


SITE_FILTERS = {
    "facebook": "site:facebook.com",
    "instagram": "site:instagram.com",
    "reddit": "site:reddit.com",
    "telegram": "site:t.me",
}


def _telegram_channel_posts(query: str, channels: list[str]) -> list[dict]:
    """Search public Telegram channel previews (t.me/s/<channel>?q=) via Jina."""
    results = []
    for chan in channels[:2]:
        try:
            r = http.get(
                f"{JINA_PREFIX}https://t.me/s/{chan}?q={quote(query)}",
                headers={"Accept": "text/markdown"},
            )
            r.raise_for_status()
            text = r.text.strip()
            if text:
                results.append(
                    {
                        "url": f"https://t.me/s/{chan}",
                        "title": f"@{chan} posts matching query",
                        "snippet": text[:1500],
                        "platform": "telegram",
                    }
                )
        except Exception:
            continue
    return results


_TG_NON_CHANNELS = {"share", "joinchat", "addstickers", "proxy", "socks"}


def _search_social(query: str, platform: str) -> str:
    """Search social media. Twitter uses Grok, others use Serper with site: filter."""
    if platform == "twitter":
        return _grok_x_search(query)

    site_filter = SITE_FILTERS.get(platform, "")
    search_query = f"{query} {site_filter}".strip()
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    r = http.post(
        "https://google.serper.dev/search",
        json={"q": search_query, "num": 8},
        headers=headers,
    )
    r.raise_for_status()
    data = r.json().get("organic", [])[:8]
    results = [
        {
            "url": item.get("link", ""),
            "title": item.get("title", ""),
            "snippet": (item.get("snippet", "") or "")[:300],
            "platform": platform,
        }
        for item in data
    ]

    if platform == "telegram":
        channels = []
        for item in results:
            m = re.search(r"t\.me/(?:s/)?([A-Za-z0-9_]{4,32})", item.get("url", ""))
            if (
                m
                and m.group(1).lower() not in _TG_NON_CHANNELS
                and m.group(1) not in channels
            ):
                channels.append(m.group(1))
        results.extend(_telegram_channel_posts(query, channels))

    return json.dumps(results, indent=2)


def _grok_x_search(query: str) -> str:
    """Search X/Twitter using Grok with OpenRouter's xAI web/X search tool."""
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
        timeout=LLM_TIMEOUT,
    )
    response = client.chat.completions.create(
        model="x-ai/grok-4.20",
        messages=[
            {
                "role": "system",
                "content": (
                    "Search X/Twitter for relevant posts, threads, and discussions. "
                    "Return the most relevant tweets with usernames, dates, and content. "
                    "Include URLs to the original tweets when possible. "
                    "If the topic concerns an Arabic-speaking region, search in both "
                    "English and Arabic and include Arabic-language posts."
                ),
            },
            {"role": "user", "content": f"Search X/Twitter for: {query}"},
        ],
        max_tokens=4096,
        extra_body={
            "plugins": [{"id": "web", "engine": "native", "max_results": 10}],
        },
    )
    content = response.choices[0].message.content or ""
    return json.dumps({"platform": "twitter", "results": content}, indent=2)


def execute_tool(name: str, args: dict) -> str:
    try:
        if name == "web_research":
            return _sonar_research(args["query"])
        elif name == "search_images":
            return _serper_search(args["query"], "images", args.get("limit", 5))
        elif name == "search_videos":
            return _search_videos(args["query"], args.get("limit", 5))
        elif name == "search_news":
            return _serper_search(args["query"], "news", args.get("limit", 5))
        elif name == "search_documents":
            return _serper_search(
                args.get("query", "") + " filetype:pdf", "search", args.get("limit", 5)
            )
        elif name == "read_page":
            return _jina_read(args["url"])
        elif name == "get_video_transcript":
            return _youtube_transcript(args["youtube_url"])
        elif name == "analyze_video_url":
            return json.dumps(
                _analyze_video_url(
                    args["youtube_url"],
                    title=args.get("title", ""),
                    source=args.get("source", ""),
                    date=args.get("date", ""),
                    duration=args.get("duration", ""),
                    thumbnail=args.get("thumbnail", ""),
                ),
                indent=2,
            )
        elif name == "search_social":
            return _search_social(args["query"], args["platform"])
        elif name == "think":
            return json.dumps(
                {"reflection_recorded": args.get("reflection", "")[:2000]}
            )
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except httpx.HTTPStatusError as e:
        return json.dumps(
            {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        )
    except (httpx.TimeoutException, httpx.ConnectError):
        return json.dumps({"error": f"timed out: {name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _build_media_appendix(images, videos, news, docs, social=None) -> str:
    """Build a semantic evidence appendix, injected server-side."""
    sections = []

    def esc(value) -> str:
        return html.escape(str(value or ""), quote=True)

    def href(value) -> str:
        value = str(value or "").strip()
        return esc(value) if value.startswith(("http://", "https://")) else ""

    def meta(*values) -> str:
        return ' <span aria-hidden="true">·</span> '.join(
            esc(value) for value in values if value
        )

    if images:
        cards = []
        for img in images[:8]:
            url = href(img.get("url"))
            title = esc(img.get("title") or "Image")
            source = img.get("source", "")
            if url:
                cards.append(
                    '<figure class="evidence-card evidence-image">'
                    f'<a class="evidence-visual" href="{url}" target="_blank" rel="noopener">'
                    f'<img src="{url}" alt="{title}" loading="lazy"></a>'
                    f"<figcaption><strong>{title}</strong>"
                    + (
                        f'<span class="evidence-meta">{esc(source)}</span>'
                        if source
                        else ""
                    )
                    + "</figcaption></figure>"
                )
        if cards:
            sections.append(
                '<section class="evidence-section"><header class="evidence-heading">'
                '<i class="ti ti-photo" aria-hidden="true"></i><div><span>Collected media</span>'
                f"<h2>Images <small>{len(cards)}</small></h2></div></header>"
                f'<div class="evidence-grid evidence-image-grid">{"".join(cards)}</div></section>'
            )

    if videos:
        cards = []
        for vid in videos[:6]:
            url = href(vid.get("url"))
            title = esc(vid.get("title") or "Video")
            duration = vid.get("duration", "")
            thumb = href(vid.get("thumbnail"))
            dossier = vid.get("dossier") or {}
            if url:
                card = ['<article class="evidence-card evidence-video">']
                if thumb:
                    card.append(
                        f'<a class="evidence-visual" href="{url}" target="_blank" rel="noopener">'
                        f'<img src="{thumb}" alt="" loading="lazy"><span class="evidence-play">'
                        '<i class="ti ti-player-play-filled" aria-hidden="true"></i></span>'
                        + (
                            f'<span class="evidence-duration">{esc(duration)}</span>'
                            if duration
                            else ""
                        )
                        + "</a>"
                    )
                card.append('<div class="evidence-body">')
                card.append(
                    f'<h3><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>'
                )
                source = dossier.get("source") or vid.get("source", "")
                date = dossier.get("date") or vid.get("date", "")
                if source or date:
                    card.append(f'<p class="evidence-meta">{meta(source, date)}</p>')
                if dossier.get("transcript"):
                    pivots = dossier.get("verification_pivots", {})
                    reverse_url = href(pivots.get("reverse_image_search"))
                    captured = dossier.get("captured_at", "")
                    card.append(
                        '<div class="evidence-dossier"><span><i class="ti ti-shield-check" '
                        'aria-hidden="true"></i> Evidence dossier</span>'
                    )
                    if captured:
                        card.append(f"<small>Captured {esc(captured)}</small>")
                    if reverse_url:
                        card.append(
                            f'<a href="{reverse_url}" target="_blank" rel="noopener">'
                            '<i class="ti ti-scan" aria-hidden="true"></i> Reverse-search thumbnail</a>'
                        )
                    card.append(
                        '<details><summary><i class="ti ti-transcript" aria-hidden="true"></i> '
                        "Timestamped transcript</summary>"
                    )
                    card.append(
                        f"<pre>{esc(dossier['transcript'][:1200])}</pre></details></div>"
                    )
                card.append("</div></article>")
                cards.append("".join(card))
        if cards:
            sections.append(
                '<section class="evidence-section"><header class="evidence-heading">'
                '<i class="ti ti-video" aria-hidden="true"></i><div><span>Watch and verify</span>'
                f"<h2>YouTube evidence <small>{len(cards)}</small></h2></div></header>"
                f'<div class="evidence-grid evidence-video-grid">{"".join(cards)}</div></section>'
            )

    if news:
        rows = []
        for item in news[:6]:
            url = href(item.get("url"))
            title = esc(item.get("title") or "Article")
            date = item.get("date", "")
            source = item.get("source", "")
            if url:
                rows.append(
                    f'<a class="evidence-row" href="{url}" target="_blank" rel="noopener">'
                    '<i class="ti ti-news" aria-hidden="true"></i><span><strong>'
                    f"{title}</strong><small>{meta(source, date)}</small></span>"
                    '<i class="ti ti-arrow-up-right" aria-hidden="true"></i></a>'
                )
        if rows:
            sections.append(
                '<section class="evidence-section"><header class="evidence-heading">'
                '<i class="ti ti-news" aria-hidden="true"></i><div><span>Published reporting</span>'
                f"<h2>Recent news <small>{len(rows)}</small></h2></div></header>"
                f'<div class="evidence-list">{"".join(rows)}</div></section>'
            )

    if docs:
        rows = []
        for doc in docs[:6]:
            url = href(doc.get("url"))
            title = esc(doc.get("title") or "Document")
            if url:
                is_pdf = ".pdf" in url.lower() or "pdf" in title.lower()
                icon = "ti-file-type-pdf" if is_pdf else "ti-file-description"
                rows.append(
                    f'<a class="evidence-row" href="{url}" target="_blank" rel="noopener">'
                    f'<i class="ti {icon}" aria-hidden="true"></i><span><strong>{title}</strong>'
                    f"<small>{meta(doc.get('source', ''), doc.get('date', ''), 'PDF' if is_pdf else 'Document')}</small></span>"
                    '<i class="ti ti-download" aria-hidden="true"></i></a>'
                )
        if rows:
            sections.append(
                '<section class="evidence-section"><header class="evidence-heading">'
                '<i class="ti ti-files" aria-hidden="true"></i><div><span>Primary material</span>'
                f"<h2>Documents and reports <small>{len(rows)}</small></h2></div></header>"
                f'<div class="evidence-list">{"".join(rows)}</div></section>'
            )

    if social:
        lines = ["---", "## Social Media"]
        for item in social:
            if isinstance(item, dict):
                if item.get("platform") == "twitter" and item.get("results"):
                    lines.append(f"### X/Twitter\n{item['results']}")
                elif item.get("url"):
                    title = item.get("title", "") or "Post"
                    snippet = item.get("snippet", "")
                    lines.append(
                        f"- [{title}]({item['url']})"
                        + (f" - *{snippet[:100]}*" if snippet else "")
                    )
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def event(event_type: str, **data) -> dict:
    return {"type": event_type, **data}


TOOL_SOURCE_MAP = {
    "web": {"web_research", "read_page"},
    "images": {"search_images"},
    "videos": {"search_videos", "get_video_transcript", "analyze_video_url"},
    "news": {"search_news"},
    "docs": {"search_documents"},
    "social": {"search_social"},
}


def _select_active_tools(sources: dict) -> tuple[list[dict], set[str]]:
    """Apply the client's source choices without disabling support tools."""
    disabled_tools = set()
    for source_key, tool_names in TOOL_SOURCE_MAP.items():
        if sources.get(source_key) is False:
            disabled_tools.update(tool_names)
    return (
        [tool for tool in TOOLS if tool["function"]["name"] not in disabled_tools],
        disabled_tools,
    )


def _select_model(config: dict) -> str:
    """Keep model selection in trusted server configuration."""
    return MODEL


def _required_source_tools(active_tool_names: set[str]) -> list[str]:
    """Return enabled collection lanes in stable display order."""
    lane_order = [
        "web_research",
        "search_images",
        "search_videos",
        "search_news",
        "search_documents",
        "search_social",
    ]
    return [name for name in lane_order if name in active_tool_names]


def _generate_plan(client, model: str, query: str) -> str:
    """Generate a research plan before executing."""
    response = client.chat.completions.create(
        model=model,
        max_tokens=512,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a research planner. Given a query, output a brief research plan "
                    "as a numbered list (3-5 steps). Each step should be one sentence. "
                    "Focus on WHAT you'll search for, not HOW. No preamble, just the list."
                ),
            },
            {"role": "user", "content": query},
        ],
    )
    return response.choices[0].message.content or ""


def _generate_followups(client, model: str, query: str) -> list[str]:
    """Generate clarifying questions before research."""
    response = client.chat.completions.create(
        model=model,
        max_tokens=256,
        messages=[
            {
                "role": "system",
                "content": (
                    "You help refine research queries. Given a query, generate exactly 3 short "
                    "follow-up questions that would help narrow the research. Format: one question "
                    "per line, no numbering, no bullets. Keep each under 60 characters."
                ),
            },
            {"role": "user", "content": query},
        ],
    )
    text = response.choices[0].message.content or ""
    return [q.strip() for q in text.strip().split("\n") if q.strip()][:3]


def _ensure_markdown(content: str) -> str:
    """If the LLM returned JSON instead of markdown, convert it."""
    stripped = content.strip()
    if stripped.startswith("```json"):
        stripped = stripped.removeprefix("```json").removesuffix("```").strip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return content
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return content
    # Convert JSON dict to markdown
    lines = []
    if isinstance(data, dict):
        for key, val in data.items():
            heading = key.replace("_", " ").title()
            lines.append(f"## {heading}")
            if isinstance(val, str):
                lines.append(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        parts = []
                        for k, v in item.items():
                            parts.append(f"**{k}**: {v}")
                        lines.append("- " + " | ".join(parts))
                    else:
                        lines.append(f"- {item}")
            elif isinstance(val, dict):
                for k, v in val.items():
                    lines.append(f"**{k}**: {v}")
            lines.append("")
    return "\n".join(lines) if lines else content


def _run_agent_loop(
    client, model, messages, active_tools, collected
) -> Generator[dict, None, str]:
    """Run the core tool-calling loop. Yields events live, returns report content."""
    iteration = 0
    max_iterations = 12

    while iteration < max_iterations:
        iteration += 1
        yield event("thinking", iteration=iteration)

        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            tools=active_tools,
            messages=messages,
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg)
            key_map = {
                "search_images": "images",
                "search_videos": "videos",
                "search_news": "news",
                "search_documents": "docs",
                "search_social": "social",
            }

            # Models occasionally emit malformed arguments; never let that kill the run
            parsed_args = {}
            for tc in msg.tool_calls:
                try:
                    parsed_args[tc.id] = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    parsed_args[tc.id] = None

            # Log all tool calls first
            for tc in msg.tool_calls:
                args = parsed_args[tc.id] or {}
                label = (
                    args.get("query")
                    or args.get("url")
                    or args.get("youtube_url")
                    or args.get("reflection", "")
                )
                yield event(
                    "tool_call", tool=tc.function.name, args=args, label=label[:120]
                )

            # Execute tools in parallel
            def _exec(tc, parsed_args=parsed_args):
                args = parsed_args[tc.id]
                if args is None:
                    return tc, json.dumps(
                        {"error": "invalid tool arguments (malformed JSON)"}
                    )
                return tc, execute_tool(tc.function.name, args)

            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(_exec, msg.tool_calls))

            for tc, result in results:
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, list):
                        if tc.function.name == "search_videos":
                            evs = []
                            _emit_video_results(parsed, collected, evs)
                            yield from evs
                        else:
                            yield event(
                                "tool_result", tool=tc.function.name, count=len(parsed)
                            )
                            if tc.function.name in key_map:
                                media_key = key_map[tc.function.name]
                                collected[media_key].extend(parsed)
                                # Stream media to UI immediately
                                if parsed:
                                    yield event(
                                        "media", kind=media_key, items=parsed[:6]
                                    )
                    elif "error" in parsed:
                        if tc.function.name == "search_social":
                            collected["social"].append(parsed)
                        yield event(
                            "tool_error", tool=tc.function.name, error=parsed["error"]
                        )
                    else:
                        title = parsed.get("title", "") or parsed.get("video_id", "")
                        yield event("tool_result", tool=tc.function.name, title=title)
                        if tc.function.name == "analyze_video_url":
                            yield event("video_dossiers", items=[parsed])
                except Exception:
                    yield event("tool_result", tool=tc.function.name)
            continue

        content = msg.content or ""

        is_planning = len(content) < 1000 and not any(
            h in content for h in ["## ", "### ", "**Summary**", "**Sources**", "**Key"]
        )

        if is_planning and iteration < max_iterations - 1:
            messages.append(msg)
            messages.append(
                {
                    "role": "user",
                    "content": "Don't narrate. Use your tools now, then write the final report when done.",
                }
            )
            continue

        # Safety net: convert JSON output to markdown
        content = _ensure_markdown(content)
        return content

    # Iteration budget exhausted: salvage the run instead of discarding it
    yield event("thinking", iteration=iteration)
    messages.append(
        {
            "role": "user",
            "content": "Stop researching. Write the final report NOW in the required markdown format, using everything gathered so far.",
        }
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=messages,
    )
    return _ensure_markdown(response.choices[0].message.content or "")


def run(query: str, config: dict = None) -> Generator[dict, None, None]:
    """Run the full research pipeline with plan, questions, research, and gap analysis."""
    config = config or {}
    knowledge_namespace = config.get("knowledge_namespace")
    sources = config.get("sources", {})
    model = _select_model(config)

    active_tools, disabled_tools = _select_active_tools(sources)

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
        timeout=LLM_TIMEOUT,
    )

    yield event("start", query=query, model=model)

    started_at = datetime.now(UTC)
    tool_log = []

    def _audit(gen):
        """Pass events through, recording tool calls for the methodology appendix."""
        while True:
            try:
                ev = next(gen)
            except StopIteration as s:
                return s.value
            if ev.get("type") == "tool_call":
                tool_log.append(
                    {
                        "ts": datetime.now(UTC).strftime("%H:%M:%S"),
                        "tool": ev.get("tool", ""),
                        "label": ev.get("label", ""),
                    }
                )
            yield ev

    # Phase 1: Run followups, knowledge check, and plan in parallel
    yield event("phase", name="Preparing research...")

    followups = []
    prior_knowledge = None
    plan = ""

    def _get_followups():
        nonlocal followups
        try:
            followups = _generate_followups(client, model, query)
        except Exception:
            pass

    def _get_knowledge():
        nonlocal prior_knowledge
        try:
            prior_knowledge = knowledge.get_prior_knowledge(
                query, namespace=knowledge_namespace
            )
        except Exception:
            pass

    def _get_plan():
        nonlocal plan
        try:
            plan = _generate_plan(client, model, query)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=3) as pool:
        pool.submit(_get_followups)
        pool.submit(_get_knowledge)
        f_plan = pool.submit(_get_plan)
        f_plan.result()  # wait for all to finish

    if followups:
        yield event("followups", questions=followups)
    if prior_knowledge:
        yield event("prior_knowledge", found=True, summary=prior_knowledge[:500])
    else:
        yield event("prior_knowledge", found=False)
    if plan:
        yield event("plan", content=plan)

    collected = {"images": [], "videos": [], "news": [], "docs": [], "social": []}

    # Videos are the core evidence lane for this tool. Run them deterministically
    # before the LLM has a chance to finish with text-only research.
    yield event("phase", name="Finding YouTube video evidence...")
    yield from _audit(_prefetch_video_evidence(query, collected, disabled_tools))

    # Phase 3: Execute research
    yield event("phase", name="Researching...")
    active_tools = _llm_tools_after_prefetch(active_tools, collected)

    # Build dynamic system prompt based on active tools
    active_tool_names = {t["function"]["name"] for t in active_tools}
    tool_lines = []
    for t in active_tools:
        name = t["function"]["name"]
        desc = t["function"]["description"].split(".")[0]
        tool_lines.append(f"- **{name}**: {desc}.")

    required_tools = _required_source_tools(active_tool_names)
    must_use_instruction = (
        f"\nYou MUST use at least {', '.join(required_tools)} before writing your report."
        if required_tools
        else ""
    )

    dynamic_prompt = f"""\
You are a deep research agent. Your job is to find, extract, and synthesize \
information from the web on any topic the user asks about.

Your available tools:
{chr(10).join(tool_lines)}

Use the enabled source tools for factual investigation.{must_use_instruction}
Between search rounds, use the think tool to note what you have learned, what is
missing or contradictory, and what to search next - avoid repeating queries.
When the topic concerns an Arabic-speaking region, also search in Arabic (Modern
Standard and local dialect terms), especially for social media and video searches -
eyewitness material is usually posted in the local language first.
Treat video results as high-value evidence leads. When search_videos returns items with
an evidence dossier, use the transcript timestamps, source/channel, publish date,
and verification pivots in your findings. For human-rights topics, prioritize
eyewitness footage, local-language titles, testimony, CCTV, drone footage, and
news clips over generic explainers.

When done, write a structured report in MARKDOWN (not JSON). Use this format:

## Summary
Key findings in 2-3 sentences.

## Sources
- [Source name](URL) - what it contributed

## Key Findings
Organized by theme with headers.

## Video Evidence Leads
For each strong video lead: title, source/channel, URL, relevant timestamped
transcript excerpt, why it matters, and what still needs verification.

## Gaps
What's still missing or unverified.

IMPORTANT: Write in plain markdown with headers, bullets, and links. Never output JSON.
Do NOT include images, videos, or documents sections. Those are appended automatically."""

    if prior_knowledge:
        dynamic_prompt += (
            "\n\n## Prior Research Context\n"
            "You have relevant knowledge from previous research sessions:\n"
            f"{prior_knowledge}\n\n"
            "Use this as context but verify key claims with fresh sources."
        )
    video_context = _prefetched_video_context(collected["videos"])
    if video_context:
        dynamic_prompt += (
            "\n\n## Prefetched Video Evidence\n"
            "These video leads were found before report writing. Use them in "
            "the Video Evidence Leads section and assess what needs verification.\n"
            f"{video_context}"
        )

    messages = [
        {"role": "system", "content": dynamic_prompt},
        {"role": "user", "content": query},
    ]

    report_content = yield from _audit(
        _run_agent_loop(client, model, messages, active_tools, collected)
    )

    # Phase 4: Gap analysis and second pass
    if report_content and "Gaps" in report_content:
        yield event("phase", name="Analyzing gaps, doing follow-up research...")
        messages.append({"role": "assistant", "content": report_content})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Look at the gaps you identified. Do ONE more round of targeted research "
                    "to fill the most important gaps. Use your tools, then rewrite the full report "
                    "incorporating the new findings. Keep the same structure."
                ),
            }
        )
        report_content = yield from _audit(
            _run_agent_loop(client, model, messages, active_tools, collected)
        )

    # Backfill: force-call any enabled media tools that returned nothing
    backfill = {
        "search_images": "images",
        "search_videos": "videos",
        "search_news": "news",
        "search_documents": "docs",
    }
    # Run all backfill calls in parallel
    backfill_needed = {
        tn: k
        for tn, k in backfill.items()
        if not collected[k] and tn not in disabled_tools
    }
    if backfill_needed:
        for tn in backfill_needed:
            tool_log.append(
                {
                    "ts": datetime.now(UTC).strftime("%H:%M:%S"),
                    "tool": tn,
                    "label": f"(backfill) {query[:80]}",
                }
            )
            yield event(
                "tool_call",
                tool=tn,
                args={"query": query},
                label=f"(backfill) {query[:80]}",
            )

        def _backfill(tool_name):
            return tool_name, execute_tool(tool_name, {"query": query, "limit": 5})

        with ThreadPoolExecutor(max_workers=4) as pool:
            bf_results = list(pool.map(_backfill, backfill_needed.keys()))

        for tool_name, result in bf_results:
            key = backfill_needed[tool_name]
            try:
                parsed = json.loads(result)
                if isinstance(parsed, list):
                    if tool_name == "search_videos":
                        bf_events = []
                        _emit_video_results(
                            parsed, collected, bf_events, tool_name=tool_name
                        )
                        yield from bf_events
                    else:
                        collected[key].extend(parsed)
                        yield event("tool_result", tool=tool_name, count=len(parsed))
                        if parsed:
                            yield event("media", kind=key, items=parsed[:6])
            except Exception:
                pass

    # Index report into knowledge graph (background, don't block response).
    # args= binds the pre-appendix content now; a lambda would race with the
    # appendix reassignment below and sometimes index media markup.
    if report_content:
        threading.Thread(
            target=knowledge.index_report,
            args=(query, report_content, knowledge_namespace),
            daemon=True,
        ).start()

    report_body = report_content or ""

    # Append media
    appendix = _build_media_appendix(
        collected["images"],
        collected["videos"],
        collected["news"],
        collected["docs"],
        collected["social"],
    )
    if appendix:
        report_content = (report_content or "").rstrip() + "\n\n" + appendix

    # Archive cited sources and append the collection record (best effort)
    if report_body:
        yield event("phase", name="Archiving cited sources...")
        try:
            archives = evidence.archive_cited(report_body)
            report_content = (
                report_content.rstrip()
                + "\n\n"
                + evidence.methodology_appendix(
                    query, model, started_at, tool_log, collected, report_body, archives
                )
            )
        except Exception as e:
            log.warning(f"Evidence appendix failed: {e}")

    yield event("report", content=report_content or "No results found.")

    yield event("done")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py 'your research query'")
        print(f"Default model: {MODEL}")
        sys.exit(1)
    query = " ".join(sys.argv[1:])
    for ev in run(query):
        if ev["type"] == "tool_call":
            print(f"  -> {ev['tool']}({ev['label']})")
        elif ev["type"] == "report":
            print(f"\n{'=' * 60}")
            print(ev["content"])
        elif ev["type"] == "start":
            print(f"\nResearch: {ev['query']}")
            print(f"Model: {ev['model']}\n")
