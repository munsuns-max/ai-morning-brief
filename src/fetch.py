import calendar
from datetime import datetime, timezone

import feedparser
import requests

from .models import Article

FEED_TIMEOUT_SECONDS = 15
FEED_USER_AGENT = "Mozilla/5.0 (compatible; AI-Morning-Brief-Bot/1.0)"


def _parse_published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, key, None)
        if struct:
            return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc)
    # 발행일을 확인할 수 없는 기사는 "최신"으로 간주하지 않는다 (오래된 글이 최신으로
    # 둔갑하는 것을 막기 위해, 못 미더우면 제외하는 쪽을 선택한다).
    return None


def fetch_feed(name: str, url: str, weight: float) -> list[Article]:
    articles: list[Article] = []
    skipped_no_date = 0

    # feedparser에 URL을 직접 넘기면 내부적으로 타임아웃 없이 무한정 대기할 수 있어,
    # 피드 서버 하나가 응답을 안 주면 전체 실행이 워크플로우 타임아웃까지 멈출 위험이
    # 있다. 그래서 직접 requests로(타임아웃 있게) 받아온 뒤 feedparser에는 내용만 넘긴다.
    try:
        resp = requests.get(url, timeout=FEED_TIMEOUT_SECONDS, headers={"User-Agent": FEED_USER_AGENT})
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - 피드 하나가 죽어도 전체 파이프라인은 계속 진행
        print(f"[fetch] '{name}' 피드 요청 실패: {exc}")
        return articles

    parsed = feedparser.parse(resp.content)

    if getattr(parsed, "bozo", False) and not parsed.entries:
        print(f"[fetch] '{name}' 피드가 비어있거나 형식 오류: {getattr(parsed, 'bozo_exception', '')}")
        return articles

    for entry in parsed.entries:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue
        published = _parse_published(entry)
        if published is None:
            skipped_no_date += 1
            continue
        summary = getattr(entry, "summary", "") or ""
        articles.append(
            Article(
                title=title,
                link=link,
                source=name,
                source_weight=weight,
                published=published,
                summary=summary,
            )
        )
    if skipped_no_date:
        print(f"[fetch] '{name}': 발행일 확인 불가로 {skipped_no_date}건 제외")
    return articles


def fetch_all(feed_configs: list[dict], lookback_hours: float) -> list[Article]:
    cutoff = datetime.now(timezone.utc).timestamp() - lookback_hours * 3600
    all_articles: list[Article] = []
    for feed in feed_configs:
        items = fetch_feed(feed["name"], feed["url"], feed.get("weight", 1))
        fresh = [a for a in items if a.published.timestamp() >= cutoff]
        print(f"[fetch] {feed['name']}: {len(items)}건 수집, {len(fresh)}건이 lookback 범위 내")
        all_articles.extend(fresh)
    return all_articles
