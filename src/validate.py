import re


def normalize_link(link: str) -> str:
    link = re.sub(r"^https?://", "", link.strip(), flags=re.IGNORECASE)
    return link.rstrip("/.,;:'\"").lower()


def validate_items(items: list[dict], candidate_links: list[str]) -> tuple[bool, list[dict]]:
    """LLM이 JSON으로 반환한 각 항목의 링크가 후보 목록에 실제로 존재하는지 검증한다.

    후보 목록에 없는 링크가 하나라도 있으면 (False, [])를 반환해 호출부가 해당
    응답 전체를 버리고 다음 폴백 단계로 넘어가도록 한다. (URL 스킴/트레일링 슬래시
    차이, 아주 긴 URL이 잘려서 인용된 경우는 정상적인 후보로 인정한다.)
    """
    normalized_candidates = [normalize_link(link) for link in candidate_links]

    for item in items:
        link_norm = normalize_link(item.get("link", ""))
        match_found = any(link_norm in c or c in link_norm for c in normalized_candidates)
        if not match_found:
            return False, []
    return True, items
