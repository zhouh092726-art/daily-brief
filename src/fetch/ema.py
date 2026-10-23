"""EMA（欧洲药品管理局）新闻列表抓取器。"""

from __future__ import annotations

import re
from html import unescape

import requests

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}
BASE = "https://www.ema.europa.eu"


def _clean(text: str) -> str:
    return WS_RE.sub(" ", TAG_RE.sub("", unescape(text or ""))).strip()


def fetch_ema(url: str, max_items: int = 10) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    items: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'<a[^>]+href="(/en/news/[a-z0-9-]{10,})"[^>]*>([^<]{10,150})</a>', resp.text
    ):
        path, title = m.group(1), _clean(m.group(2))
        if path in seen or not title:
            continue
        seen.add(path)
        items.append(
            {
                "title": title,
                "abstract": "",
                "url": f"{BASE}{path}",
                "published": "",  # 列表页无日期，正文按需提取
            }
        )
        if len(items) >= max_items:
            break
    return items
