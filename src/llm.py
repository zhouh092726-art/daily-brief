"""OpenAI 两层管道：mini 模型打分筛选 + 主力模型生成阅读卡片。

支持 --mock 模式：不调用 API，用启发式规则填充，
便于本地端到端测试整条流水线。
"""

from __future__ import annotations

import json
import re
import time

from .models import Item

SCORE_SYSTEM = """你是一名文献情报分析员，服务对象是一位合成生物学背景的博士研究员。
他关注：合成生物学核心技术（基因线路、最小基因组、无细胞系统、定向进化）、
基因编辑（CRISPR、先导编辑、碱基编辑）、蛋白质设计（AlphaFold 方向）、
诺奖级发现的后续进展、创新药与新疗法。
请根据标题和摘要，为每条文献评估"对该读者的重要性"（0-100 分）。
打分基准：90+ 领域重大突破或里程碑；70-89 有明确技术或应用价值；50-69 相关但常规；<50 弱相关。
只输出 JSON：{"scores": [{"id": "...", "score": 0, "reason": "15字以内理由"}]}"""

CARD_SYSTEM = """你是科研阅读卡片生成器。为给定文献生成一张中文阅读卡片，供合成生物学博士快速判断是否精读。
只输出 JSON，字段：
- "title_cn": 中文标题（准确专业，不逐字直译）
- "one_liner": 一句话结论，60 字以内，直接说发现了什么
- "key_findings": 2-3 条关键发现或方法，每条 50 字以内
- "why_it_matters": 为什么重要，80 字以内，结合读者方向
- "priority": 精读建议 1-3 的整数（3=强烈建议精读，1=了解即可）
要求：忠于摘要原文，不添加摘要之外的信息；保留 CRISPR、mRNA 等通用英文缩写。"""

ABSTRACT_LIMIT = 1200


def _client():
    from openai import OpenAI

    return OpenAI()  # 从 OPENAI_API_KEY 环境变量读取


def _chat_json(client, model: str, system: str, user: str, retries: int = 3) -> dict:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            return json.loads(resp.choices[0].message.content or "{}")
        except Exception as err:  # noqa: BLE001
            last_err = err
            time.sleep(2**attempt)
    raise RuntimeError(f"OpenAI 调用失败（{retries} 次重试后）: {last_err}")


# ---------------------------------------------------------------- 打分层

def score_items(items: list[Item], cfg: dict, mock: bool = False) -> dict[str, tuple[int, str]]:
    """返回 {item_id: (score, reason)}。"""
    if mock:
        return _mock_scores(items, cfg)

    client = _client()
    model = cfg["llm"]["score_model"]
    batch_size = 20
    scores: dict[str, tuple[int, str]] = {}

    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        payload = [
            {
                "id": it.id,
                "title": it.title,
                "abstract": it.abstract[:ABSTRACT_LIMIT],
            }
            for it in batch
        ]
        result = _chat_json(
            client, model, SCORE_SYSTEM, json.dumps(payload, ensure_ascii=False)
        )
        for entry in result.get("scores", []):
            try:
                scores[entry["id"]] = (int(entry.get("score", 0)), str(entry.get("reason", "")))
            except (KeyError, ValueError):
                continue
    return scores


def _mock_scores(items: list[Item], cfg: dict) -> dict[str, tuple[int, str]]:
    keywords = [k.lower() for k in cfg.get("scoring", {}).get("boost_keywords", [])]
    scores: dict[str, tuple[int, str]] = {}
    for it in items:
        haystack = f"{it.title} {it.abstract}".lower()
        hits = sum(1 for k in keywords if k in haystack)
        score = min(40 + hits * 12, 95)
        scores[it.id] = (score, f"mock：命中 {hits} 个关键词")
    return scores


# ---------------------------------------------------------------- 卡片层

def generate_card(item: Item, cfg: dict, mock: bool = False) -> dict:
    """为单条文献生成卡片字段 dict。"""
    if mock:
        return _mock_card(item)

    client = _client()
    model = cfg["llm"]["card_model"]
    payload = {
        "title": item.title,
        "abstract": item.abstract,
        "journal": item.journal,
        "published": item.published,
    }
    result = _chat_json(
        client, model, CARD_SYSTEM, json.dumps(payload, ensure_ascii=False)
    )
    return {
        "title_cn": str(result.get("title_cn", item.title)),
        "one_liner": str(result.get("one_liner", "")),
        "key_findings": [str(x) for x in result.get("key_findings", [])][:3],
        "why_it_matters": str(result.get("why_it_matters", "")),
        "priority": max(1, min(3, int(result.get("priority", 1)))),
    }


def _sentences(text: str, n: int) -> list[str]:
    parts = re.split(r"(?<=[.!?。！])\s+", text.strip())
    return [p for p in parts if p][:n]


def _mock_card(item: Item) -> dict:
    sents = _sentences(item.abstract, 4)
    return {
        "title_cn": item.title,
        "one_liner": sents[0] if sents else "",
        "key_findings": sents[1:3],
        "why_it_matters": "（mock 模式占位文本，用于测试流水线，未调用 LLM）",
        "priority": 1,
    }
