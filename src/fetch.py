import calendar
from datetime import datetime, timezone

import feedparser

from .models import Article

FEED_TIMEOUT_SECONDS = 15


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
    try:
        parsed = feedparser.parse(url, agent="Mozilla/5.0 (AI-Morning-Brief-Bot)")
    except Exception as exc:  # noqa: BLE001 - 피드 하나가 죽어도 전체 파이프라인은 계속 진행
        print(f"[fetch] '{name}' 피드 파싱 실패: {exc}")
        return articles

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
