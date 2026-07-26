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


def filter_relevant(
    articles: list[Article],
    high_keywords: list[str],
    medium_keywords: list[str],
) -> list[Article]:
    """제목/요약에 AI 관련 키워드가 하나도 없는 기사는 후보에서 제외한다.

    소스 가중치나 최신성만으로 후보에 오르는 것을 막아, 실제로 AI 관련성이
    확인되지 않은 기사(예: 'anthropic'이 철학 용어로 쓰인 글)가 AI 뉴스처럼
    브리핑에 섞여 들어가는 것을 방지한다.
    """
    relevant = []
    for article in articles:
        text = f"{article.title} {article.summary}"
        if _keyword_score(text, high_keywords, medium_keywords) > 0:
            relevant.append(article)
    return relevant


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
