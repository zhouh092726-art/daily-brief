"""每日流水线编排：抓取 → 去重 → 打分 → 卡片 → 落盘 → 渲染。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .config import load_config
from .dedup import load_all_days, load_seen_ids, save_day
from .fetch.biorxiv import fetch_biorxiv
from .fetch.pubmed import fetch_pubmed
from .llm import generate_card, score_items
from .models import Card, Item
from .render import render_site

SECTION_PAPERS = {"id": "papers", "title": "文献 · 合成生物学"}


def _fetch_all(cfg: dict) -> list[dict]:
    fcfg = cfg.get("fetch", {})
    raw: list[dict] = []

    pub = fcfg.get("pubmed", {})
    if pub.get("enabled", True):
        print(f"[fetch] PubMed: {len(pub.get('queries', []))} 个查询，回看 {fcfg.get('lookback_days', 3)} 天")
        raw += fetch_pubmed(
            pub.get("queries", []),
            fcfg.get("lookback_days", 3),
            pub.get("retmax", 100),
        )
        print(f"[fetch] PubMed 返回 {len(raw)} 条")

    bio = fcfg.get("biorxiv", {})
    if bio.get("enabled", True):
        print("[fetch] bioRxiv 分页抓取中…")
        pre = len(raw)
        raw += fetch_biorxiv(
            bio.get("servers", ["biorxiv"]),
            bio.get("categories", []),
            bio.get("keyword_filter", []),
            fcfg.get("lookback_days", 3),
        )
        print(f"[fetch] bioRxiv 返回 {len(raw) - pre} 条")
    return raw


def run(mock: bool = False, date_override: str | None = None) -> None:
    cfg = load_config()
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    date_str = date_override or now.strftime("%Y-%m-%d")
    print(f"[pipeline] 生成 {date_str} 简报{'（mock 模式）' if mock else ''}")

    raw = _fetch_all(cfg)
    seen = load_seen_ids()
    fresh = [d for d in raw if d["id"] not in seen]
    print(f"[dedup] 抓取 {len(raw)} 条，其中新增 {len(fresh)} 条（过滤历史 {len(raw) - len(fresh)} 条）")

    items = [Item.from_dict(d) for d in fresh if d.get("title") and d.get("abstract")]

    if not items:
        print("[pipeline] 今日无新增文献，仅刷新站点")
        payload = {
            "date": date_str,
            "generated_at": now.isoformat(),
            "fetched_ids": [d["id"] for d in raw],
            "stats": {"fetched": len(raw), "kept": 0, "mock": mock, "new_items": 0},
            "sections": [{**SECTION_PAPERS, "cards": []}],
        }
        save_day(date_str, payload)
        render_site(cfg["site"], load_all_days())
        return

    lcfg = cfg.get("llm", {})
    to_score = items[: lcfg.get("max_score_items", 120)]
    print(f"[score] 送入打分 {len(to_score)} 条")
    scores = score_items(to_score, cfg, mock=mock)

    ranked = sorted(
        to_score, key=lambda it: scores.get(it.id, (0, ""))[0], reverse=True
    )
    top = ranked[: lcfg.get("top_n", 20)]
    print(f"[score] 保留前 {len(top)} 条生成卡片")

    cards: list[Card] = []
    for i, it in enumerate(top, 1):
        print(f"[card] ({i}/{len(top)}) {it.title[:60]}…")
        fields = generate_card(it, cfg, mock=mock)
        sc, reason = scores.get(it.id, (0, ""))
        cards.append(Card(item=it, score=sc, score_reason=reason, **fields))

    payload = {
        "date": date_str,
        "generated_at": now.isoformat(),
        "fetched_ids": [d["id"] for d in raw],
        "stats": {
            "fetched": len(raw),
            "new_items": len(items),
            "kept": len(cards),
            "mock": mock,
        },
        "sections": [{**SECTION_PAPERS, "cards": [c.to_dict() for c in cards]}],
    }
    save_day(date_str, payload)
    render_site(cfg["site"], load_all_days())
    print(f"[done] 站点已生成 → site/（{len(cards)} 张卡片）")
