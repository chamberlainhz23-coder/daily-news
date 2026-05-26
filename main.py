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
    "https://www.reutersagency.com/feed/?best-topics=political-general&post_type=best",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://www.ft.com/rss/world",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.npr.org/1004/rss.xml",
    "https://www.scmp.com/rss/91/feed",
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
        "us ",
        "washington",
        "tariff",
        "trade war",
        "taiwan",
        "south china sea",
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
    for _, words in FOCUS_KEYWORDS.items():
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
    ]
    score += sum(3 for term in high_impact_terms if term in lowered)
    return score


def fetch_news(feeds: List[str], max_per_feed: int = 12) -> List[Dict[str, Any]]:
    articles: List[Dict[str, Any]] = []
    seen_links = set()
    timeout = int(os.getenv("HTTP_TIMEOUT_SECONDS", "20"))

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
                    "summary": summary[:900],
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
        fingerprint = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", article["title"].lower())[:80]
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
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    max_items = int(os.getenv("MAX_NEWS_ITEMS", "10"))

    selected = articles[: min(max_items * 2, 24)]
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
        "你是一名资深国际政经分析师。请从候选新闻中筛选不超过10条最重要新闻，"
        "用中文生成克制、直接、专业的每日简报。不要娱乐八卦、低价值社会新闻、标题党和重复新闻。"
        "优先选择对中国、全球格局、金融市场、战争地缘、AI科技产业有实质影响的新闻。"
    )
    user_prompt = f"""
今天日期：{datetime.now().strftime("%Y-%m-%d")}

输出要求：
1. 最多10条，宁缺毋滥。
2. 每条必须包含：
   - 标题
   - 发生了什么
   - 为什么重要
   - 对中国/全球格局的影响
   - 来源链接
3. 不要写“以下是”“总体来看”等套话。
4. 如果候选新闻价值不足，可以少于10条。
5. 按重要性从高到低排序。

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
    }

    response = requests.post(url, headers=headers, json=data, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"大模型接口失败: HTTP {response.status_code} | {response.text[:1000]}")

    result = response.json()
    return result["choices"][0]["message"]["content"].strip()


def push_wecom(content: str) -> bool:
    webhook = os.getenv("WECOM_WEBHOOK", "").strip()
    if not webhook:
        return False

    payload = {"msgtype": "markdown", "markdown": {"content": content[:3900]}}
    response = requests.post(webhook, json=payload, timeout=20)
    if response.status_code != 200:
        print(f"[ERROR] 企业微信推送失败: HTTP {response.status_code} | {response.text}", file=sys.stderr)
        return False

    data = response.json()
    if data.get("errcode") != 0:
        print(f"[ERROR] 企业微信推送失败: {data}", file=sys.stderr)
        return False
    return True


def push_serverchan(content: str) -> bool:
    send_key = os.getenv("SERVERCHAN_SENDKEY", "").strip()
    if not send_key:
        return False

    url = f"https://sctapi.ftqq.com/{send_key}.send"
    data = {"title": "每日全球重要新闻", "desp": content}
    response = requests.post(url, data=data, timeout=20)
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
    return f"## 每日全球重要新闻｜{date_text}\n\n{briefing}"


def main() -> None:
    feeds = parse_feeds()
    if not feeds:
        raise RuntimeError("没有可用新闻源。请配置 NEWS_FEEDS。")

    articles = fetch_news(feeds)
    articles = sorted(articles, key=lambda x: x["score"], reverse=True)
    max_candidates = int(os.getenv("MAX_CANDIDATES", "30"))
    articles = articles[:max_candidates]

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
