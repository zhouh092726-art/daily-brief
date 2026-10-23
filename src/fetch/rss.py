"""通用 RSS/Atom 抓取器（feedparser），支持关键词过滤。"""

from __future__ import annotations

import re
import time
from html import unescape

import feedparser
import requests

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}


def _clean(text: str) -> str:
    return WS_RE.sub(" ", TAG_RE.sub("", unescape(text or ""))).strip()


def _iso(entry) -> str:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return time.strftime("%Y-%m-%d", parsed)
    return ""


def _keyword_match(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)


def fetch_rss(
    url: str, keywords: list[str] | None = None, max_items: int = 20
) -> list[dict]:
    """抓取单个 RSS 源，返回原始 Item 字典列表（不含 source/section，由调用方补齐）。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as err:  # noqa: BLE001
        print(f"[rss] 抓取失败 {url}: {err}")
        return []

    items: list[dict] = []
    for entry in feed.entries:
        title = _clean(getattr(entry, "title", ""))
        link = getattr(entry, "link", "")
        if not title or not link:
            continue
        summary = _clean(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        if keywords and not _keyword_match(f"{title} {summary}", keywords):
            continue
        items.append(
            {
                "title": title,
                "abstract": summary[:1500],
                "url": link,
                "published": _iso(entry),
            }
        )
        if len(items) >= max_items:
            break
    return items
