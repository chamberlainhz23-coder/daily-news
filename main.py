import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import feedparser
import requests
from dotenv import load_dotenv


load_dotenv()


DEFAULT_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://www.reutersagency.com/feed/?best-topics=political-general&post_type=best",
    "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://www.ft.com/rss/world",
    "https://www.ft.com/rss/companies/technology",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.npr.org/1004/rss.xml",
    "https://feeds.npr.org/1019/rss.xml",
    "https://www.scmp.com/rss/91/feed",
    "https://www.scmp.com/rss/4/feed",
    "https://www.chinadaily.com.cn/rss/world_rss.xml",
    "https://www.chinadaily.com.cn/rss/business_rss.xml",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
]

FOCUS_KEYWORDS = {
    "international_politics": [
        "president",
        "election",
        "parliament",
        "government",
        "summit",
        "minister",
        "sanction",
        "diplomacy",
        "treaty",
        "nato",
        "united nations",
        "g7",
        "g20",
    ],
    "china_us": [
        "china",
        "chinese",
        "beijing",
        "xi jinping",
        "united states",
        "u.s.",
        "washington",
        "tariff",
        "trade war",
        "taiwan",
        "south china sea",
        "export control",
    ],
    "war_geo": [
        "war",
        "conflict",
        "military",
        "missile",
        "drone",
        "ukraine",
        "russia",
        "israel",
        "gaza",
        "iran",
        "red sea",
        "ceasefire",
        "attack",
    ],
    "economy_finance": [
        "market",
        "stocks",
        "bond",
        "federal reserve",
        "central bank",
        "inflation",
        "oil",
        "currency",
        "trade",
        "supply chain",
        "gdp",
        "debt",
        "recession",
    ],
    "ai_tech": [
        "ai",
        "artificial intelligence",
        "chip",
        "semiconductor",
        "nvidia",
        "openai",
        "technology",
        "export control",
        "data center",
        "cloud",
    ],
}

BLOCK_KEYWORDS = [
    "celebrity",
    "movie",
    "music",
    "fashion",
    "sport",
    "football",
    "nba",
    "viral",
    "tiktok trend",
    "horoscope",
]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        print(f"[WARN] {name} 不是有效整数，已回退到默认值 {default}", file=sys.stderr)
        return default


def parse_feeds() -> List[str]:
    raw = os.getenv("NEWS_FEEDS", "").strip()
    if not raw:
        return DEFAULT_FEEDS
    return [item.strip() for item in raw.splitlines() if item.strip() and not item.strip().startswith("#")]


def normalize_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_date(entry: Any) -> Optional[str]:
    for key in ("published", "updated", "created"):
        value = getattr(entry, key, None)
        if not value:
            continue
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return None


def article_id(title: str, link: str) -> str:
    source = f"{title.lower().strip()}|{link.lower().strip()}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def keyword_score(text: str) -> int:
    lowered = f" {text.lower()} "
    if any(word in lowered for word in BLOCK_KEYWORDS):
        return -100

    score = 0
    for words in FOCUS_KEYWORDS.values():
        matches = sum(1 for word in words if word in lowered)
        if matches:
            score += 6 + matches * 2

    high_impact_terms = [
        "china",
        "u.s.",
        "united states",
        "russia",
        "ukraine",
        "taiwan",
        "iran",
        "israel",
        "nato",
        "sanction",
        "tariff",
        "semiconductor",
        "federal reserve",
        "central bank",
        "export control",
    ]
    score += sum(3 for term in high_impact_terms if term in lowered)
    return score


def fetch_news(feeds: List[str], max_per_feed: int) -> List[Dict[str, Any]]:
    articles: List[Dict[str, Any]] = []
    seen_links = set()

    for feed_url in feeds:
        try:
            parsed = feedparser.parse(feed_url, request_headers={"User-Agent": "daily-global-news-bot/1.0"})
            if parsed.bozo:
                print(f"[WARN] RSS 解析可能异常: {feed_url} | {parsed.bozo_exception}", file=sys.stderr)
        except Exception as exc:
            print(f"[ERROR] RSS 抓取失败: {feed_url} | {exc}", file=sys.stderr)
            continue

        for entry in parsed.entries[:max_per_feed]:
            title = normalize_text(getattr(entry, "title", ""))
            link = normalize_text(getattr(entry, "link", ""))
            summary = normalize_text(getattr(entry, "summary", ""))

            if not title or not link or link in seen_links:
                continue
            seen_links.add(link)

            text = f"{title}. {summary}"
            score = keyword_score(text)
            if score <= 0:
                continue

            articles.append(
                {
                    "id": article_id(title, link),
                    "title": title,
                    "link": link,
                    "summary": summary[:1800],
                    "published": parse_date(entry),
                    "source_feed": feed_url,
                    "score": score,
                }
            )

    return deduplicate_articles(articles)


def deduplicate_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen_fingerprints = set()

    for article in sorted(articles, key=lambda x: x["score"], reverse=True):
        fingerprint = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", article["title"].lower())[:100]
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)
        deduped.append(article)

    return deduped


def call_llm(articles: List[Dict[str, Any]]) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY。请在本地 .env 或 GitHub Secrets 中配置。")

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    max_items = env_int("MAX_NEWS_ITEMS", 12)
    max_tokens = env_int("LLM_MAX_TOKENS", 4200)
    detail_level = os.getenv("BRIEFING_DETAIL_LEVEL", "deep").strip() or "deep"

    selected = articles[: min(max_items * 5, 80)]
    payload_articles = [
        {
            "title": item["title"],
            "summary": item["summary"],
            "link": item["link"],
            "published": item["published"],
            "score": item["score"],
        }
        for item in selected
    ]

    system_prompt = (
        "你是一名资深国际政经分析师，服务对象是需要快速决策的中文读者。"
        "你的任务不是泛泛摘要，而是筛出真正重要的国际新闻，并给出简明、硬信息密度高、"
        "带判断的中文简报。避免空话、套话、鸡汤和无效背景。"
    )
    user_prompt = f"""
今天日期：{datetime.now().strftime("%Y-%m-%d")}
内容密度要求：至少比常规晨报详细 3 倍。
输出要求：
1. 输出 8 到 {max_items} 条，优先重要性，不要为了凑数塞低价值新闻。
2. 每条必须包含以下字段，且每个字段都要有实质内容：
   - 标题
   - 发生了什么：2到4句，讲清事件、主体、动作、时间。
   - 为什么重要：2到4句，直接讲战略意义、政策意义或市场意义。
   - 对中国的影响：2到4句，不能只写“值得关注”。
   - 对全球格局/市场的影响：2到4句。
   - 后续观察点：列出2到3个变量。
   - 来源链接
3. 保持中文、专业、直接、克制，不要写“以下是”“总体来看”“可以看出”。
4. 按重要性排序。
5. 对同一事件的重复报道只保留信息量最高的一条。
6. 如果某条新闻事实不足，不要强行拔高。
7. detail_level={detail_level}，默认按深度版执行。

候选新闻 JSON：
{json.dumps(payload_articles, ensure_ascii=False, indent=2)}
"""

    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }

    response = requests.post(url, headers=headers, json=data, timeout=90)
    if response.status_code >= 400:
        raise RuntimeError(f"大模型接口失败: HTTP {response.status_code} | {response.text[:1200]}")

    result = response.json()
    return result["choices"][0]["message"]["content"].strip()


def split_markdown_message(content: str, limit: int) -> List[str]:
    if len(content) <= limit:
        return [content]

    lines = content.splitlines()
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for line in lines:
        add_len = len(line) + 1
        if current and current_len + add_len > limit:
            chunks.append("\n".join(current).strip())
            current = [line]
            current_len = add_len
        else:
            current.append(line)
            current_len += add_len

    if current:
        chunks.append("\n".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def push_wecom(content: str) -> bool:
    webhook = os.getenv("WECOM_WEBHOOK", "").strip()
    if not webhook:
        return False

    for idx, chunk in enumerate(split_markdown_message(content, 3600), start=1):
        payload = {"msgtype": "markdown", "markdown": {"content": chunk}}
        response = requests.post(webhook, json=payload, timeout=20)
        if response.status_code != 200:
            print(f"[ERROR] 企业微信推送失败: HTTP {response.status_code} | 第 {idx} 段 | {response.text}", file=sys.stderr)
            return False

        data = response.json()
        if data.get("errcode") != 0:
            print(f"[ERROR] 企业微信推送失败: 第 {idx} 段 | {data}", file=sys.stderr)
            return False
    return True


def push_serverchan(content: str) -> bool:
    send_key = os.getenv("SERVERCHAN_SENDKEY", "").strip()
    if not send_key:
        return False

    url = f"https://sctapi.ftqq.com/{send_key}.send"
    response = requests.post(url, data={"title": "每日全球重要新闻", "desp": content}, timeout=20)
    if response.status_code != 200:
        print(f"[ERROR] Server酱推送失败: HTTP {response.status_code} | {response.text}", file=sys.stderr)
        return False

    result = response.json()
    if result.get("code") not in (0, None):
        print(f"[ERROR] Server酱推送失败: {result}", file=sys.stderr)
        return False
    return True


def push_message(content: str) -> None:
    dry_run = env_bool("DRY_RUN", False)
    if dry_run:
        print(content)
        return

    if push_wecom(content):
        print("[OK] 已推送到企业微信")
        return

    if push_serverchan(content):
        print("[OK] 已通过 Server酱推送")
        return

    raise RuntimeError("推送失败：请至少配置 WECOM_WEBHOOK 或 SERVERCHAN_SENDKEY，并检查密钥是否有效。")


def build_message(briefing: str) -> str:
    date_text = datetime.now().strftime("%Y-%m-%d")
    return f"## 每日全球重要新闻 | {date_text}\n\n{briefing}"


def main() -> None:
    feeds = parse_feeds()
    if not feeds:
        raise RuntimeError("没有可用新闻源。请配置 NEWS_FEEDS。")

    max_per_feed = env_int("MAX_PER_FEED", 20)
    max_candidates = env_int("MAX_CANDIDATES", 80)

    articles = fetch_news(feeds, max_per_feed=max_per_feed)
    articles = sorted(articles, key=lambda x: x["score"], reverse=True)[:max_candidates]

    if not articles:
        raise RuntimeError("未抓取到符合条件的新闻。请检查 RSS 源或关键词。")

    print(f"[INFO] 候选新闻数量: {len(articles)}")
    briefing = call_llm(articles)
    message = build_message(briefing)
    push_message(message)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        sys.exit(1)
