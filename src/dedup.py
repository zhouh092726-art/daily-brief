"""去重与每日数据存取。

历史数据以 JSON 快照形式提交在 data/YYYY-MM-DD/brief.json，
新抓取的条目与全部历史 id 比对，避免重复出卡。
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR


def load_seen_ids() -> set[str]:
    seen: set[str] = set()
    if not DATA_DIR.exists():
        return seen
    for day_dir in sorted(DATA_DIR.iterdir()):
        brief = day_dir / "brief.json"
        if not brief.is_file():
            continue
        try:
            data = json.loads(brief.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for section in data.get("sections", []):
            for card in section.get("cards", []):
                item = card.get("item", {})
                if item.get("id"):
                    seen.add(item["id"])
        for fid in data.get("fetched_ids", []):
            seen.add(fid)
    return seen


def load_all_days() -> list[dict]:
    """按日期倒序返回所有历史 brief。"""
    days: list[dict] = []
    if not DATA_DIR.exists():
        return days
    for day_dir in sorted(DATA_DIR.iterdir(), reverse=True):
        brief = day_dir / "brief.json"
        if not brief.is_file():
            continue
        try:
            days.append(json.loads(brief.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return days


def save_day(date_str: str, payload: dict) -> Path:
    day_dir = DATA_DIR / date_str
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / "brief.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
