"""静态站点渲染：读取 data/ 下所有日期的 brief，生成 index / day / archive 页面。"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import SITE_DIR, STATIC_DIR, TEMPLATES_DIR

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

COMING_SECTIONS = [
    {"id": "policy", "title": "政策公告", "desc": "央行 · 深圳 · 国家医保局"},
    {"id": "tech", "title": "科技", "desc": "AI · 英伟达 · 芯片 · 汽车"},
    {"id": "finance", "title": "财经", "desc": "今日金价 · 监管公告"},
]


def _stars(n: int) -> str:
    n = max(1, min(3, int(n)))
    return "★" * n + "☆" * (3 - n)


def _date_display(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{date_str} {WEEKDAYS[d.weekday()]}"
    except ValueError:
        return date_str


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    env.filters["stars"] = _stars
    env.filters["date_display"] = _date_display
    return env


def render_site(site_cfg: dict, days: list[dict]) -> Path:
    env = _env()
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    (SITE_DIR / "day").mkdir(parents=True)
    if (STATIC_DIR / "style.css").exists():
        shutil.copytree(STATIC_DIR, SITE_DIR / "static")

    common = {
        "site_name": site_cfg.get("name", "每日情报"),
        "tagline": site_cfg.get("tagline", ""),
    }

    for day in days:
        html = env.get_template("day.html").render(
            **common,
            day=day,
            days=days,
            coming=COMING_SECTIONS,
            asset="../static/",
            home="../",
            archive_link="../archive.html",
            day_link_prefix="",
        )
        (SITE_DIR / "day" / f"{day['date']}.html").write_text(html, encoding="utf-8")

    latest = days[0] if days else None
    root_paths = {
        "asset": "static/",
        "home": "./",
        "archive_link": "archive.html",
        "day_link_prefix": "day/",
    }
    (SITE_DIR / "index.html").write_text(
        env.get_template("index.html").render(
            **common, day=latest, days=days, coming=COMING_SECTIONS, **root_paths
        ),
        encoding="utf-8",
    )
    (SITE_DIR / "archive.html").write_text(
        env.get_template("archive.html").render(**common, days=days, **root_paths),
        encoding="utf-8",
    )
    return SITE_DIR
