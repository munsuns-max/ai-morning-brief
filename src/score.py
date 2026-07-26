from .models import Article

W_SOURCE = 1.0
W_KEYWORD = 1.0
W_CLUSTER = 2.0
W_RECENCY = 2.0

HIGH_KEYWORD_POINTS = 3.0
MEDIUM_KEYWORD_POINTS = 1.5


def _keyword_score(text: str, high_keywords: list[str], medium_keywords: list[str]) -> float:
    lowered = text.lower()
    score = 0.0
    for kw in high_keywords:
        if kw.lower() in lowered:
            score += HIGH_KEYWORD_POINTS
    for kw in medium_keywords:
        if kw.lower() in lowered:
            score += MEDIUM_KEYWORD_POINTS
    return score


def score_articles(
    articles: list[Article],
    high_keywords: list[str],
    medium_keywords: list[str],
    lookback_hours: float,
) -> list[Article]:
    for article in articles:
        text = f"{article.title} {article.summary}"
        keyword_pts = _keyword_score(text, high_keywords, medium_keywords)
        recency_pts = max(0.0, 1.0 - article.hours_old / lookback_hours)
        cluster_pts = min(article.cluster_size, 5)  # 5개 매체 이상은 더 줘도 변별력 없음

        article.score = (
            article.source_weight * W_SOURCE
            + keyword_pts * W_KEYWORD
            + cluster_pts * W_CLUSTER
            + recency_pts * W_RECENCY
        )

    return sorted(articles, key=lambda a: a.score, reverse=True)
