from rapidfuzz import fuzz

from .models import Article


def dedupe(articles: list[Article], similarity_threshold: float) -> list[Article]:
    """제목 유사도 기반으로 같은 사건을 다루는 기사를 하나로 묶는다.

    대표 기사는 source_weight가 가장 높은 것을 남기고, 몇 개의 매체가
    같은 사건을 보도했는지(cluster_size)를 중요도 신호로 함께 기록한다.
    """
    clusters: list[Article] = []

    # source_weight가 높은 기사를 먼저 대표로 세울 수 있도록 정렬
    ordered = sorted(articles, key=lambda a: a.source_weight, reverse=True)

    for article in ordered:
        matched = None
        for rep in clusters:
            similarity = fuzz.token_sort_ratio(article.title.lower(), rep.title.lower())
            if similarity >= similarity_threshold:
                matched = rep
                break
        if matched is None:
            clusters.append(article)
        else:
            matched.cluster_size += 1

    return clusters
