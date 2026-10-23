"""每日流水线编排：抓取 → 去重 → 分板块打分 → 卡片 → 落盘 → 渲染。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import load_config
from .dedup import load_all_days, load_seen_ids, save_day
from .fetch.biorxiv import fetch_biorxiv
from .fetch.ema import fetch_ema
from .fetch.govcn import extract_abstract, fetch_nhsa, fetch_pbc
from .fetch.pubmed import fetch_pubmed
from .fetch.rss import fetch_rss
from .llm import generate_card, score_items
from .models import Card, Item
from .render import render_site

SECTION_ORDER = ["papers", "drugs", "policy", "tech"]
ENRICH_SOURCES = {"pbc", "nhsa", "ema"}  # 列表页无摘要、需按需抓正文的源


def _short_id(kind: str, url: str) -> str:
    return f"{kind}:{hashlib.md5(url.encode()).hexdigest()[:16]}"


def _fetch_sources(cfg: dict) -> dict[str, list[dict]]:
    """抓取全部源，返回 {section: [item dict, ...]}。"""
    per_section: dict[str, list[dict]] = defaultdict(list)

    fcfg = cfg.get("fetch", {})
    papers: list[dict] = []
    pub = fcfg.get("pubmed", {})
    if pub.get("enabled", True):
        print(f"[fetch] PubMed: {len(pub.get('queries', []))} 个查询")
        papers += fetch_pubmed(
            pub.get("queries", []),
            fcfg.get("lookback_days", 3),
            pub.get("retmax", 100),
        )
    bio = fcfg.get("biorxiv", {})
    if bio.get("enabled", True):
        print("[fetch] bioRxiv 分页抓取中…")
        pre = len(papers)
        papers += fetch_biorxiv(
            bio.get("servers", ["biorxiv"]),
            bio.get("categories", []),
            bio.get("keyword_filter", []),
            fcfg.get("lookback_days", 3),
        )
        print(f"[fetch] 文献共 {len(papers)} 条（bioRxiv {len(papers) - pre}）")
    per_section["papers"] = papers

    for src in cfg.get("sources", []):
        kind = src.get("kind")
        url = src.get("url", "")
        try:
            if kind == "rss":
                raw = fetch_rss(url, src.get("keywords"), src.get("max_items", 20))
            elif kind == "pbc":
                raw = fetch_pbc(url, src.get("max_items", 15))
            elif kind == "nhsa":
                raw = fetch_nhsa(url, src.get("max_items", 10))
            elif kind == "ema":
                raw = fetch_ema(url, src.get("max_items", 10))
            else:
                continue
        except Exception as err:  # noqa: BLE001
            print(f"[fetch] {src.get('name', kind)} 失败: {err}")
            continue
        for d in raw:
            d.update(
                id=_short_id(kind, d["url"]),
                source=kind,
                source_label=src.get("name", kind),
                tier=src.get("tier", "official"),
                journal=src.get("name", kind),
                authors="",
                doi=None,
            )
        per_section[src.get("section", "tech")] += raw
        print(f"[fetch] {src.get('name', kind)}: {len(raw)} 条")
    return per_section


def _build_cards(
    section_id: str, title: str, items: list[Item], cfg: dict, mock: bool
) -> list[Card]:
    if not items:
        return []
    lcfg = cfg.get("llm", {})
    scfg = (cfg.get("sections") or {}).get(section_id, {})
    top_n = scfg.get("top_n", lcfg.get("top_n", 20))
    to_score = items[: lcfg.get("max_score_items", 120)]

    print(f"[score] {section_id}: {len(to_score)} 条送入打分")
    scores = score_items(to_score, cfg, section=section_id, mock=mock)
    ranked = sorted(to_score, key=lambda it: scores.get(it.id, (0, ""))[0], reverse=True)
    top = ranked[:top_n]

    cards: list[Card] = []
    for i, it in enumerate(top, 1):
        if not it.abstract and it.source in ENRICH_SOURCES:
            print(f"[enrich] ({i}/{len(top)}) 补充正文: {it.title[:50]}…")
            it.abstract = extract_abstract(it.url)
        print(f"[card] {section_id} ({i}/{len(top)}) {it.title[:50]}…")
        fields = generate_card(it, cfg, section=section_id, mock=mock)
        sc, reason = scores.get(it.id, (0, ""))
        cards.append(Card(item=it, score=sc, score_reason=reason, **fields))
    return cards


def run(mock: bool = False, date_override: str | None = None) -> None:
    cfg = load_config()
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    date_str = date_override or now.strftime("%Y-%m-%d")
    print(f"[pipeline] 生成 {date_str} 简报{'（mock 模式）' if mock else ''}")

    per_section = _fetch_sources(cfg)
    seen = load_seen_ids()

    total_fetched = 0
    total_new = 0
    all_fetched_ids: list[str] = []
    sections_payload: list[dict] = []

    for section_id in SECTION_ORDER:
        scfg = (cfg.get("sections") or {}).get(section_id)
        if scfg is None:
            continue
        raw = per_section.get(section_id, [])
        total_fetched += len(raw)
        all_fetched_ids += [d["id"] for d in raw]
        fresh = [d for d in raw if d["id"] not in seen]
        total_new += len(fresh)
        print(f"[dedup] {section_id}: 抓取 {len(raw)}，新增 {len(fresh)}")

        items = [Item.from_dict(d) for d in fresh if d.get("title")]
        cards = _build_cards(section_id, scfg.get("title", section_id), items, cfg, mock)
        sections_payload.append(
            {"id": section_id, "title": scfg.get("title", section_id), "cards": [c.to_dict() for c in cards]}
        )

    total_cards = sum(len(s["cards"]) for s in sections_payload)
    payload = {
        "date": date_str,
        "generated_at": now.isoformat(),
        "fetched_ids": all_fetched_ids,
        "stats": {
            "fetched": total_fetched,
            "new_items": total_new,
            "kept": total_cards,
            "mock": mock,
        },
        "sections": sections_payload,
    }
    save_day(date_str, payload)
    render_site(cfg["site"], load_all_days())
    print(f"[done] 站点已生成 → site/（{total_cards} 张卡片，4 板块）")
