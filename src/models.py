from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Item:
    """一条从官方源抓到的原始信息。"""

    id: str  # 如 "pubmed:39012345" / "biorxiv:10.1101/2026.10.20.123456"
    source: str  # pubmed | biorxiv
    source_label: str  # PubMed | bioRxiv
    tier: str  # official | curated
    title: str
    abstract: str
    url: str
    journal: str
    authors: str
    published: str  # ISO 日期
    doi: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Item":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Card:
    """一张阅读卡片：Item + 打分 + LLM 生成的中文卡片内容。"""

    item: Item
    score: int = 0
    score_reason: str = ""
    title_cn: str = ""
    one_liner: str = ""
    key_findings: list[str] = field(default_factory=list)
    why_it_matters: str = ""
    priority: int = 1  # 精读建议 1-3

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["item"] = self.item.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Card":
        item = Item.from_dict(d["item"])
        return cls(
            item=item,
            score=d.get("score", 0),
            score_reason=d.get("score_reason", ""),
            title_cn=d.get("title_cn", item.title),
            one_liner=d.get("one_liner", ""),
            key_findings=d.get("key_findings", []),
            why_it_matters=d.get("why_it_matters", ""),
            priority=d.get("priority", 1),
        )
