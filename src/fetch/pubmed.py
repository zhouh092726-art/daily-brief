"""PubMed 官方 E-utilities 抓取器。

文档: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import requests

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

HEADERS = {"User-Agent": "daily-brief/0.1 (personal literature digest)"}

MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def _text(node: ET.Element | None) -> str:
    return "".join(node.itertext()).strip() if node is not None else ""


def _iso_date(pub_date: ET.Element | None) -> str:
    if pub_date is None:
        return ""
    year = _text(pub_date.find("Year"))
    month = _text(pub_date.find("Month"))
    day = _text(pub_date.find("Day"))
    if not year:
        return _text(pub_date)[:10]
    month = MONTHS.get(month, month if month.isdigit() else "01")
    day = day if day.isdigit() else "01"
    return f"{year}-{month or '01'}-{day or '01'}"


def _parse_article(article: ET.Element) -> dict | None:
    citation = article.find("MedlineCitation")
    if citation is None:
        return None
    pmid = _text(citation.find("PMID"))
    art = citation.find("Article")
    if art is None or not pmid:
        return None

    title = _text(art.find("ArticleTitle"))
    abstract_parts = []
    for ab in art.findall("./Abstract/AbstractText"):
        label = ab.get("Label")
        seg = _text(ab)
        if label:
            seg = f"{label}: {seg}"
        if seg:
            abstract_parts.append(seg)
    abstract = "\n".join(abstract_parts)

    journal = _text(art.find("./Journal/Title"))

    authors = []
    for author in art.findall("./AuthorList/Author"):
        last = _text(author.find("LastName"))
        collective = _text(author.find("CollectiveName"))
        if last:
            authors.append(last)
        elif collective:
            authors.append(collective)
        if len(authors) >= 3:
            break
    author_str = ", ".join(authors)
    if len(art.findall("./AuthorList/Author")) > 3:
        author_str += ", et al."

    doi = ""
    for aid in art.findall("./ELocationID"):
        if aid.get("EIdType") == "doi":
            doi = _text(aid)
    if not doi:
        for aid in citation.findall("./ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)

    if not title or not abstract:
        return None

    return {
        "id": f"pubmed:{pmid}",
        "source": "pubmed",
        "source_label": "PubMed",
        "tier": "official",
        "title": title,
        "abstract": abstract,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "doi": doi or None,
        "journal": journal,
        "authors": author_str,
        "published": _iso_date(art.find("./Journal/JournalIssue/PubDate")),
    }


def fetch_pubmed(queries: list[str], lookback_days: int, retmax: int = 100) -> list[dict]:
    """按查询词抓取最近 N 天入库（edat）的文献，返回原始 Item 字典列表。"""
    pmids: list[str] = []
    for query in queries:
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": retmax,
            "reldate": lookback_days,
            "datetype": "edat",
            "sort": "pub_date",
        }
        resp = requests.get(ESEARCH_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        result = resp.json().get("esearchresult", {})
        ids = result.get("idlist", [])
        for pid in ids:
            if pid not in pmids:
                pmids.append(pid)
        time.sleep(0.4)

    if not pmids:
        return []

    items: list[dict] = []
    for i in range(0, len(pmids), 150):
        batch = pmids[i : i + 150]
        resp = requests.get(
            EFETCH_URL,
            params={"db": "pubmed", "id": ",".join(batch), "retmode": "xml"},
            headers=HEADERS,
            timeout=60,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        for article in root.findall("./PubmedArticle"):
            parsed = _parse_article(article)
            if parsed:
                items.append(parsed)
        time.sleep(0.4)
    return items
