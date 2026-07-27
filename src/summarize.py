import json
import os
import re
import time
from datetime import datetime, timezone

import requests

from . import usage_tracker, validate
from .models import Article

HTTP_TIMEOUT = 20
MAX_RETRIES = 2

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


_HNRSS_BOILERPLATE = re.compile(
    r"^(Article URL|Comments URL|Points|# Comments)\s*:", re.IGNORECASE
)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _clean_snippet(text: str) -> str:
    """HTML을 제거하고, hnrss가 붙이는 'Article URL / Points / # Comments' 같은
    메타데이터 줄(사람이 읽을 요약과 무관)을 걸러낸다."""
    text = re.sub(r"</p>|<br\s*/?>", "\n", text or "", flags=re.IGNORECASE)
    text = _strip_html(text)
    lines = [ln.strip() for ln in text.split("\n")]
    kept = [ln for ln in lines if ln and not _HNRSS_BOILERPLATE.match(ln)]
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def _render_brief(overview: str, items: list[dict]) -> str:
    """텔레그램에 보낼 최종 텍스트를 파이썬 코드가 직접, 항상 같은 형식으로 조립한다.

    LLM이 만들든(Gemini/Groq) 규칙기반 폴백이 만들든 이 함수 하나만 거치므로,
    볼드 제목/줄바꿈/항목 간 빈 줄이 항상 100% 동일하게 강제된다.
    """
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    parts = [f"*🌅 AI Morning Brief - {today}*"]
    if overview:
        parts.append(overview.strip())
    for item in items:
        title = item["title"].strip().replace("\n", " ")
        summary = item["summary"].strip()
        parts.append(f"🔹 *{title}*\n{summary}\n\n출처: {item['source']} | {item['link']}")
    return "\n\n".join(parts)


def _build_prompt(articles: list[Article], max_items_in_brief: int) -> str:
    max_items = min(len(articles), max_items_in_brief)
    lines = [
        "너는 개인용 'AI 업계 아침 브리핑'을 작성하는 편집자야.",
        "아래는 지난 24~30시간 동안 수집된 AI 관련 기사 후보 목록이야 (이미 중요도순으로 정렬됨, "
        "cluster_size는 몇 개 매체가 같은 소식을 다뤘는지를 뜻함). 후보는 이미 AI 관련 키워드 매칭을 "
        "통과한 것들이지만, 그래도 실제로 오늘 다룰 가치가 없다고 판단되면 제외해도 돼.",
        "",
        "다음 JSON 스키마로만 응답해. 코드블록 표시(```)나 그 외 설명 텍스트는 절대 포함하지 말고 "
        "순수 JSON 하나만 반환해:",
        '{"overview": "오늘 브리핑 전체에 대한 1~2문장 총평 (한국어)", '
        '"items": [{"title": "한국어로 자연스럽게 의역한 제목", '
        '"summary": "2~3문장 한국어 요약", "link": "후보 목록에 있는 링크를 그대로 복사"}]}',
        f"- items는 중요도순으로 최대 {max_items}개. 후보 중 실제로 다룰 가치가 있는 게 {max_items}개보다 "
        "적으면 절대 억지로 개수를 채우지 말고 있는 만큼만 넣어 — 개수를 맞추려고 사소한 내용을 "
        "부풀리거나 하나의 기사를 여러 항목으로 쪼개지 마.",
        "- link는 반드시 아래 후보 목록에 있는 링크를 글자 하나도 바꾸지 말고 그대로 복사해서 써. "
        "후보 목록에 없는 링크나 사실, 수치, 인용을 새로 만들어내지 마. 확실하지 않으면 차라리 "
        "그 항목을 빼.",
        "- 비슷한 내용을 다루는 후보는 하나로 합쳐서 items의 한 항목으로만 다뤄.",
        "- title에는 줄바꿈을 넣지 마.",
        "",
        "기사 후보 목록:",
    ]
    for idx, a in enumerate(articles, start=1):
        snippet = _clean_snippet(a.summary)[:400]
        lines.append(
            f"{idx}. 제목: {a.title}\n"
            f"   출처: {a.source} (신뢰도 가중치 {a.source_weight}, 유사보도 {a.cluster_size}건)\n"
            f"   링크: {a.link}\n"
            f"   내용 일부: {snippet}"
        )
    lines.append("")
    lines.append(f"오늘 날짜: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d')}")
    return "\n".join(lines)


def _post_with_retry(url: str, **kwargs) -> requests.Response:
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, timeout=HTTP_TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            # 상태 코드만으로는 429/4xx의 실제 원인(예: 어떤 quota가 초과됐는지)을 알 수
            # 없어서, 응답 본문을 함께 로그로 남긴다 (키 자체는 이미 마스킹되어 있음).
            body = exc.response.text[:500] if exc.response is not None else ""
            print(f"[summarize] 요청 실패 (시도 {attempt}/{MAX_RETRIES}): {exc} | 응답 본문: {body}")
            if attempt < MAX_RETRIES:
                time.sleep(2)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f"[summarize] 요청 실패 (시도 {attempt}/{MAX_RETRIES}): {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(2)
    raise last_exc


def _call_gemini(prompt: str, api_key: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    resp = _post_with_retry(
        url,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
    )
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_groq(prompt: str, api_key: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    resp = _post_with_retry(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        },
    )
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _parse_llm_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # 지시에도 불구하고 코드펜스로 감싸는 모델이 있어 방어적으로 벗겨낸다.
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    data = json.loads(cleaned)
    if not isinstance(data, dict) or "items" not in data:
        raise ValueError("응답에 'items' 필드가 없음")
    items = data["items"]
    if not isinstance(items, list):
        raise ValueError("'items'가 배열이 아님")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("items의 원소가 객체가 아님")
        for key in ("title", "summary", "link"):
            if not item.get(key):
                raise ValueError(f"item에 '{key}' 필드가 없거나 비어있음")
    return {"overview": str(data.get("overview") or "").strip(), "items": items}


def _find_article_by_link(articles: list[Article], link: str) -> Article | None:
    link_norm = validate.normalize_link(link)
    for a in articles:
        a_norm = validate.normalize_link(a.link)
        if link_norm in a_norm or a_norm in link_norm:
            return a
    return None


def _try_render_llm_output(
    raw_text: str, articles: list[Article], candidate_links: list[str]
) -> tuple[str, list[Article]] | None:
    """LLM의 원시 JSON 응답을 검증하고 텔레그램 텍스트로 렌더링한다.

    JSON 파싱 실패, 필수 필드 누락, 또는 후보 목록에 없는 링크가 하나라도 있으면
    None을 반환해 호출부가 다음 폴백 단계로 넘어가도록 한다.
    """
    try:
        parsed = _parse_llm_json(raw_text)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"[summarize] LLM JSON 파싱/구조 검증 실패: {exc}")
        return None

    valid, validated_items = validate.validate_items(parsed["items"], candidate_links)
    if not valid:
        return None

    render_items = []
    included_articles = []
    for item in validated_items:
        article = _find_article_by_link(articles, item["link"])
        if article is None:
            continue  # validate_items를 통과했다면 이론상 항상 찾아야 하지만 방어적으로 스킵
        render_items.append(
            {
                "title": item["title"],
                "summary": item["summary"],
                "source": article.source,
                "link": article.link,
            }
        )
        included_articles.append(article)

    return _render_brief(parsed["overview"], render_items), included_articles


def _extractive_fallback(articles: list[Article], max_items: int) -> tuple[str, list[Article]]:
    """LLM 두 곳 모두 실패했을 때의 최종 폴백: 규칙 기반 추출 + 무료 기계번역.

    품질은 LLM 요약보다 떨어지지만 API 키/비용 없이 100% 동작을 보장하고,
    최종 렌더링은 LLM 경로와 동일한 _render_brief()를 거치므로 형식은 항상 같다.
    """
    try:
        from deep_translator import GoogleTranslator

        translator = GoogleTranslator(source="auto", target="ko")
        translate = translator.translate
    except Exception as exc:  # noqa: BLE001
        print(f"[summarize] 번역기 초기화 실패, 원문 그대로 사용: {exc}")
        translate = None

    included = articles[:max_items]
    render_items = []
    for a in included:
        title_ko = a.title
        snippet_ko = _clean_snippet(a.summary)[:200]
        if translate:
            try:
                title_ko = translate(a.title)
                if snippet_ko:
                    snippet_ko = translate(snippet_ko)
            except Exception as exc:  # noqa: BLE001
                print(f"[summarize] 번역 실패, 원문 유지: {exc}")
        render_items.append(
            {"title": title_ko, "summary": snippet_ko, "source": a.source, "link": a.link}
        )

    overview = "(⚠️ 이 브리핑은 LLM 요약 없이 자동 생성되었습니다)"
    return _render_brief(overview, render_items), included


def summarize_articles(articles: list[Article], settings: dict) -> tuple[str, str, list[Article]]:
    """반환값: (브리핑 텍스트, 사용된 티어 이름, 실제로 브리핑에 포함된 기사 목록)

    '포함된 기사 목록'은 이후 sent_history에 기록되어 다음 실행에서 같은 뉴스가
    다시 보내지지 않도록 하는 데 쓰인다. LLM 티어의 경우, 실제로 검증을 통과한
    항목에 해당하는 후보만 포함된 것으로 간주한다.
    """
    if not articles:
        return _render_brief("오늘은 눈에 띄는 AI 뉴스가 없습니다.", []), "empty", []

    max_items = settings.get("pipeline", {}).get("max_items_in_brief", 8)
    limits = settings.get("usage_limits", {})
    state = usage_tracker.load()
    prompt = _build_prompt(articles, max_items)
    candidate_links = [a.link for a in articles]

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key and usage_tracker.under_soft_cap(
        state, "gemini", limits.get("gemini_daily_soft_cap", 20)
    ):
        gemini_raw = None
        try:
            gemini_raw = _call_gemini(prompt, gemini_key)
            usage_tracker.record_call(state, "gemini")
            usage_tracker.save(state)
        except Exception as exc:  # noqa: BLE001
            print(f"[summarize] Gemini 호출 실패, Groq으로 폴백: {exc}")
        if gemini_raw is not None:
            result = _try_render_llm_output(gemini_raw, articles, candidate_links)
            if result is not None:
                return result[0], "gemini", result[1]
            print("[summarize] Gemini 응답 검증 실패 - Groq으로 폴백")

    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key and usage_tracker.under_soft_cap(
        state, "groq", limits.get("groq_daily_soft_cap", 20)
    ):
        groq_raw = None
        try:
            groq_raw = _call_groq(prompt, groq_key)
            usage_tracker.record_call(state, "groq")
            usage_tracker.save(state)
        except Exception as exc:  # noqa: BLE001
            print(f"[summarize] Groq 호출 실패, 규칙 기반 폴백으로 전환: {exc}")
        if groq_raw is not None:
            result = _try_render_llm_output(groq_raw, articles, candidate_links)
            if result is not None:
                return result[0], "groq", result[1]
            print("[summarize] Groq 응답 검증 실패 - 규칙 기반 폴백으로 전환")

    usage_tracker.save(state)
    text, included = _extractive_fallback(articles, max_items)
    return text, "fallback", included
