import json
import os
from datetime import datetime, timedelta, timezone

from rapidfuzz import fuzz

from .models import Article

HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state", "sent_history.json")
RETENTION_DAYS = 3


def load() -> list[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save(history: list[dict]) -> None:
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def prune(history: list[dict]) -> list[dict]:
    """RETENTION_DAYS보다 오래된 기록은 지운다 (파일이 무한정 커지는 것 방지)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    kept = []
    for entry in history:
        try:
            sent_at = datetime.fromisoformat(entry["sent_at"])
        except (KeyError, ValueError, TypeError):
            continue
        if sent_at >= cutoff:
            kept.append(entry)
    return kept


def filter_unsent(
    articles: list[Article], history: list[dict], similarity_threshold: float
) -> list[Article]:
    """링크가 정확히 같거나 제목이 이미 보낸 기사와 매우 유사하면 후보에서 제외한다.

    lookback_hours가 실행 주기보다 길어서 생기는 겹치는 구간 때문에, 어제 이미
    보낸 기사가 오늘도 '새 뉴스'처럼 다시 후보에 오르는 것을 막기 위함이다.
    """
    sent_links = {e["link"] for e in history if "link" in e}
    sent_titles = [e["title"].lower() for e in history if "title" in e]

    unsent = []
    for article in articles:
        if article.link in sent_links:
            continue
        title_lower = article.title.lower()
        if any(
            fuzz.token_sort_ratio(title_lower, sent_title) >= similarity_threshold
            for sent_title in sent_titles
        ):
            continue
        unsent.append(article)
    return unsent


def record_sent(history: list[dict], articles: list[Article]) -> list[dict]:
    """실제로 브리핑에 포함되어 전송된 기사만 기록한다 (후보로만 고려된 것 X)."""
    now = datetime.now(timezone.utc).isoformat()
    for article in articles:
        history.append({"link": article.link, "title": article.title, "sent_at": now})
    return history
