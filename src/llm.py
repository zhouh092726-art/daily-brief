"""LLM 两层管道：mini 模型打分筛选 + 主力模型生成阅读卡片。

按板块（papers/drugs/policy/tech）使用不同的读者画像与卡片风格。
支持 --mock 模式：不调用 API，用启发式规则填充，便于本地端到端测试。
"""

from __future__ import annotations

import json
import re
import time

from .models import Item

READER = "一位合成生物学背景的博士研究员，在中国深圳"

SECTION_PROFILES = {
    "papers": (
        "他关注：合成生物学核心技术（基因线路、最小基因组、无细胞系统、定向进化）、"
        "基因编辑（CRISPR、先导编辑、碱基编辑）、蛋白质设计（AlphaFold 方向）、"
        "诺奖级发现的后续进展、创新药与新疗法。"
    ),
    "drugs": (
        "他关注：创新药获批（FDA/EMA/NMPA）、重要临床试验结果、"
        "新疗法（细胞治疗、基因治疗、mRNA）、知名药企（跨国 MNC 与国内创新药企）的重大发布与财报。"
    ),
    "policy": (
        "他关注：央行的货币政策与重要金融公告、国家医保局的目录调整/集采/支付政策、"
        "生物医药相关监管政策、深圳与全国的重要民生政策。"
    ),
    "tech": (
        "他关注：AI 大模型与重大产品发布（OpenAI、DeepMind、Anthropic 等）、"
        "英伟达与芯片半导体产业链、智能汽车与自动驾驶。"
    ),
}

SECTION_CARD_HINTS = {
    "papers": "这是一篇学术论文。one_liner 直接说研究发现了什么；key_findings 聚焦方法与结果。",
    "drugs": "这是一条新药/疗法/药企动态。one_liner 直接说发生了什么（谁、什么药、什么事）；key_findings 聚焦关键数据、适应症与临床意义。",
    "policy": "这是一条政府或监管机构公告。one_liner 直接说政策发生了什么变化；key_findings 聚焦变化内容、生效时间、影响范围。",
    "tech": "这是一条科技产业新闻。one_liner 直接说发生了什么；key_findings 聚焦产品、数据与产业影响。",
}

SCORE_SYSTEM_TMPL = """你是一名情报分析员，服务对象是{reader}。
{profile}
请根据标题和摘要（可能为空），为每条信息评估"对该读者的重要性"（0-100 分）。
打分基准：90+ 重大突破或里程碑，必须知道；70-89 有明确价值；50-69 相关但常规；<50 弱相关。
只输出 JSON：{{"scores": [{{"id": "...", "score": 0, "reason": "15字以内理由"}}]}}"""

CARD_SYSTEM_TMPL = """你是情报阅读卡片生成器。为给定信息生成一张中文阅读卡片，供{reader}快速判断是否值得深入了解。
{hint}
只输出 JSON，字段：
- "title_cn": 中文标题（准确专业，不逐字直译；若原文即中文则原样保留）
- "one_liner": 一句话结论，60 字以内
- "key_findings": 2-3 条关键要点，每条 50 字以内
- "why_it_matters": 为什么重要，80 字以内，结合读者方向
- "priority": 值得深入了解的建议等级 1-3 的整数（3=强烈建议，1=了解即可）
要求：忠于原文（标题与摘要），不添加原文之外的信息；若摘要为空，仅依据标题生成，没把握的字段填空字符串；
保留 CRISPR、mRNA、FDA 等通用英文缩写。"""

ABSTRACT_LIMIT = 1200


def _client(cfg: dict):
    from openai import OpenAI

    base_url = (cfg.get("llm") or {}).get("base_url") or None
    return OpenAI(base_url=base_url)  # key 从 OPENAI_API_KEY 环境变量读取


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
    raise RuntimeError(f"LLM 调用失败（{retries} 次重试后）: {last_err}")


# ---------------------------------------------------------------- 打分层

def score_items(
    items: list[Item], cfg: dict, section: str = "papers", mock: bool = False
) -> dict[str, tuple[int, str]]:
    """返回 {item_id: (score, reason)}。"""
    if mock:
        return _mock_scores(items, cfg)

    client = _client(cfg)
    model = cfg["llm"]["score_model"]
    system = SCORE_SYSTEM_TMPL.format(
        reader=READER, profile=SECTION_PROFILES.get(section, "")
    )
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
            client, model, system, json.dumps(payload, ensure_ascii=False)
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

def generate_card(
    item: Item, cfg: dict, section: str = "papers", mock: bool = False
) -> dict:
    """为单条信息生成卡片字段 dict。"""
    if mock:
        return _mock_card(item)

    client = _client(cfg)
    model = cfg["llm"]["card_model"]
    system = CARD_SYSTEM_TMPL.format(
        reader=READER, hint=SECTION_CARD_HINTS.get(section, "")
    )
    payload = {
        "title": item.title,
        "abstract": item.abstract,
        "source": item.source_label,
        "published": item.published,
    }
    result = _chat_json(
        client, model, system, json.dumps(payload, ensure_ascii=False)
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
    sents = _sentences(item.abstract or item.title, 4)
    return {
        "title_cn": item.title,
        "one_liner": sents[0] if sents else "",
        "key_findings": sents[1:3],
        "why_it_matters": "（mock 模式占位文本，用于测试流水线，未调用 LLM）",
        "priority": 1,
    }
