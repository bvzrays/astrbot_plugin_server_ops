"""Web tools: web_search (Brave API) and web_fetch (URL content extraction)."""
from dataclasses import dataclass, field
from astrbot.api.event import AstrMessageEvent
from .base import OpsTool
import html
import json
import re
import httpx
from urllib.parse import urlparse

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


def _strip_tags(text: str) -> str:
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _to_markdown(raw_html: str) -> str:
    text = re.sub(r'<a\s+[^>]*href=["\'](.*?)["\'][^>]*>([\s\S]*?)</a>',
                  lambda m: f'[{_strip_tags(m[2])}]({m[1]})', raw_html, flags=re.I)
    text = re.sub(r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
                  lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n', text, flags=re.I)
    text = re.sub(r'<li[^>]*>([\s\S]*?)</li>', lambda m: f'\n- {_strip_tags(m[1])}', text, flags=re.I)
    text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
    text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
    return _normalize(_strip_tags(text))


@dataclass
class WebSearchTool(OpsTool):
    name: str = "web_search"
    description: str = "使用 Brave Search API 搜索网络内容，返回标题、URL 和摘要。需配置 web_search_api_key。"
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索词"},
            "count": {"type": "number", "description": "结果数（1-10，默认 6）"}
        },
        "required": ["query"],
    })
    api_key: str = ""
    max_results: int = 6

    async def run(self, event: AstrMessageEvent, query: str, count: float = None):
        if not self.api_key:
            return "Error: web_search_api_key not configured in plugin settings."
        n = min(int(count or self.max_results), 10)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                )
                r.raise_for_status()
            results = r.json().get("web", {}).get("results", [])
            if not results:
                return f"No results for: {query}"
            lines = [f"Search results for: {query}\n"]
            for i, item in enumerate(results[:n], 1):
                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
                if desc := item.get("description"):
                    lines.append(f"   {desc}")
            return "\n".join(lines)
        except Exception as e:
            return f"Search error: {e}"


@dataclass
class WebFetchTool(OpsTool):
    name: str = "web_fetch"
    description: str = "抓取指定 URL 并提取可读正文（HTML → Markdown）。适用于查看文档、博客、Status 页面等。"
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要抓取的 URL"},
            "mode": {"type": "string", "enum": ["markdown", "text"], "description": "提取格式"}
        },
        "required": ["url"],
    })
    max_chars: int = 10000

    async def run(self, event: AstrMessageEvent, url: str, mode: str = "markdown"):
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return f"Error: Only http/https URLs are allowed."
        except Exception as e:
            return f"Error: Invalid URL: {e}"
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            text = r.text
            if "application/json" in ctype:
                text = json.dumps(r.json(), indent=2, ensure_ascii=False)
            elif "text/html" in ctype:
                text = _to_markdown(text) if mode == "markdown" else _normalize(_strip_tags(text))
            if len(text) > self.max_chars:
                text = text[:self.max_chars] + f"\n\n... (truncated at {self.max_chars} chars)"
            return f"URL: {url}\n\n{text}"
        except Exception as e:
            return f"Error fetching {url}: {e}"
