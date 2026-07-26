import re

_LINK_RE = re.compile(r"https?://[^\s)>\]},'\"]+")


def normalize_link(link: str) -> str:
    link = re.sub(r"^https?://", "", link.strip(), flags=re.IGNORECASE)
    return link.rstrip("/.,;:'\"").lower()


def extract_links(text: str) -> list[str]:
    return [normalize_link(m) for m in _LINK_RE.findall(text)]


def validate_and_collect_used(text: str, candidate_links: list[str]) -> tuple[bool, set[str]]:
    """LLM 출력에 등장한 링크가 모두 후보 목록에 실제로 존재하는지 검증한다.

    후보 목록에 없는 링크가 하나라도 있으면 (False, set())을 반환해 호출부가
    해당 응답을 버리고 다음 폴백 단계로 넘어가도록 한다. (URL 스킴/트레일링
    슬래시 차이, 아주 긴 URL이 잘려서 인용된 경우는 정상적인 후보로 인정한다.)
    """
    normalized_candidates = [normalize_link(link) for link in candidate_links]
    mentioned = extract_links(text)

    used: set[str] = set()
    for link in mentioned:
        match = next(
            (c for c in normalized_candidates if link in c or c in link),
            None,
        )
        if match is None:
            return False, set()
        used.add(match)
    return True, used
