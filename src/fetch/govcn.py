"""中国政府网站列表页抓取器：央行（人民银行）、国家医保局。

以及统一的正文提取工具（用于给入选条目补充摘要）。
"""

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


def _clean(text: str) -> str:
    return WS_RE.sub(" ", TAG_RE.sub("", unescape(text or ""))).strip()


def extract_abstract(url: str, limit: int = 900) -> str:
    """抓取文章页提取摘要：优先 meta description，退化为正文前 N 字。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        html = resp.text
    except Exception as err:  # noqa: BLE001
        print(f"[gov] 正文抓取失败 {url}: {err}")
        return ""

    for pattern in (
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{20,})["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']{20,})["\']',
    ):
        m = re.search(pattern, html, re.I)
        if m:
            return _clean(m.group(1))[:limit]

    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return _clean(body)[:limit]


def fetch_pbc(url: str, max_items: int = 15) -> list[dict]:
    """人民银行沟通交流列表页。日期编码在链接路径里（YYYYMMDD…）。"""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    items: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'href="(/goutongjiaoliu/113456/113469/(\d{8})\d*/index\.html)"[^>]*title="([^"]+)"',
        resp.text,
    ):
        path, ymd, title = m.group(1), m.group(2), _clean(m.group(3))
        if path in seen or not title:
            continue
        seen.add(path)
        items.append(
            {
                "title": title,
                "abstract": "",  # 正文在入选后按需提取
                "url": f"https://www.pbc.gov.cn{path}",
                "published": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}",
            }
        )
        if len(items) >= max_items:
            break
    return items


def fetch_nhsa(url: str, max_items: int = 10) -> list[dict]:
    """国家医保局列表页（医保动态 col14）。日期在 /art/YYYY/M/D/ 路径里。"""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    items: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'href="(/art/(\d{4})/(\d{1,2})/(\d{1,2})/art_[^"]+\.html)"[^>]*title="([^"]+)"',
        resp.text,
    ):
        path, y, mo, d, title = m.groups()
        if path in seen or not _clean(title):
            continue
        seen.add(path)
        items.append(
            {
                "title": _clean(title),
                "abstract": "",
                "url": f"https://www.nhsa.gov.cn{path}",
                "published": f"{y}-{int(mo):02d}-{int(d):02d}",
            }
        )
        if len(items) >= max_items:
            break
    return items
