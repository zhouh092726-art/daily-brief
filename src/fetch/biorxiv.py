"""bioRxiv 官方 API 抓取器。

文档: https://api.biorxiv.org/
按日期窗口分页拉取 details，再按 category / 关键词过滤。
"""

from __future__ import annotations

import re
import time
from datetime import date, timedelta

import requests

API_URL = "https://api.biorxiv.org/details/{server}/{start}/{end}/{cursor}"
HEADERS = {"User-Agent": "daily-brief/0.1 (personal literature digest)"}
PAGE_SIZE = 100
MAX_PAGES = 40
TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return TAG_RE.sub("", text or "").strip()


def _matches(item: dict, categories: set[str], keywords: list[str]) -> bool:
    if item.get("category", "").lower().replace(" ", "_") in categories:
        return True
    haystack = f"{item.get('title', '')} {item.get('abstract', '')}".lower()
    return any(k.lower() in haystack for k in keywords)


def fetch_biorxiv(
    servers: list[str],
    categories: list[str],
    keywords: list[str],
    lookback_days: int,
) -> list[dict]:
    """抓取最近 N 天指定 category / 关键词的预印本。"""
    end = date.today()
    start = end - timedelta(days=lookback_days)
    cat_set = {c.lower().replace(" ", "_") for c in categories}
    seen: set[str] = set()
    items: list[dict] = []

    for server in servers:
        cursor = 0
        total: int | None = None
        for _ in range(MAX_PAGES):
            url = API_URL.format(
                server=server, start=start.isoformat(), end=end.isoformat(), cursor=cursor
            )
            resp = requests.get(url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
            collection = payload.get("collection", [])
            if total is None:
                total = int(payload.get("messages", [{}])[0].get("count", 0))
            for entry in collection:
                doi = entry.get("doi", "")
                if not doi or doi in seen:
                    continue
                if _matches(entry, cat_set, keywords):
                    seen.add(doi)
                    items.append(
                        {
                            "id": f"biorxiv:{doi}",
                            "source": "biorxiv",
                            "source_label": "bioRxiv",
                            "tier": "official",
                            "title": _clean(entry.get("title", "")),
                            "abstract": _clean(entry.get("abstract", "")),
                            "url": f"https://www.biorxiv.org/content/{doi}v1",
                            "doi": doi,
                            "journal": f"bioRxiv · {entry.get('category', '')}",
                            "authors": _clean(entry.get("authors", "").replace(";", ", "))[:80],
                            "published": (entry.get("published", "") or "")[:10],
                        }
                    )
            cursor += len(collection)
            if not collection or (total is not None and cursor >= total):
                break
            time.sleep(0.4)
    return items
