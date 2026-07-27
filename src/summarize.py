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


def _post_with_retry(url: str, **kwargs) -> requests.Response:
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, timeout=HTTP_TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f"[summarize] 요청 실패 (시도 {attempt}/{MAX_RETRIES}): {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(2)
    raise last_exc


def _build_prompt(articles: list[Article], max_items_in_brief: int) -> str:
    max_items = min(len(articles), max_items_in_brief)
    lines = [
        "너는 개인용 'AI 업계 아침 브리핑'을 작성하는 편집자야.",
        "아래는 지난 24~30시간 동안 수집된 AI 관련 기사 후보 목록이야 (이미 중요도순으로 정렬됨, "
        "cluster_size는 몇 개 매체가 같은 소식을 다뤘는지를 뜻함). 후보는 이미 AI 관련 키워드 매칭을 "
        "통과한 것들이지만, 그래도 실제로 오늘 다룰 가치가 없다고 판단되면 제외해도 돼.",
        "이 중에서 실제로 중요한 소식만 골라 한국어로 브리핑을 작성해줘.",
        "",
        "출력 형식 규칙:",
        "- 텔레그램 메시지로 바로 보낼 것이므로 마크다운은 굵게(*텍스트*)만 사용하고, "
        "  #, ##, ```, 하이픈 목록 같은 문법은 쓰지 마.",
        "- 맨 위에 '*🌅 AI Morning Brief - {오늘 날짜}*' 제목을 넣고, 그 아래 한두 문장으로 "
        "오늘의 총평을 적어줘. 그리고 빈 줄을 하나 넣어.",
        f"- 이어서 중요도순으로 최대 {max_items}개 항목을 작성. "
        f"후보 중 실제로 다룰 가치가 있는 게 {max_items}개보다 적으면 절대 억지로 개수를 채우지 말고 "
        "있는 만큼만 써 — 개수를 맞추려고 사소한 내용을 부풀리거나 하나의 기사를 여러 항목으로 "
        "쪼개지 마.",
        "- 각 항목은 반드시 아래 4줄 형식을 그대로 지켜서 써 (줄바꿈 위치 포함):",
        "    🔹 *제목(한국어로 자연스럽게 의역)*",
        "    2~3문장 한국어 요약",
        "    (빈 줄)",
        "    출처: 매체명 | 링크",
        "- 항목과 항목 사이에는 반드시 빈 줄을 하나 더 넣어서 구분해 (즉, 한 항목의 '출처' 줄과 "
        "다음 항목의 '🔹 제목' 줄 사이에 빈 줄이 하나 있어야 함).",
        "- 링크는 반드시 아래 후보 목록에 있는 링크를 글자 하나도 바꾸지 말고 그대로 복사해서 써. "
        "후보 목록에 없는 링크나 사실, 수치, 인용을 새로 만들어내지 마. 확실하지 않으면 차라리 "
        "그 항목을 빼.",
        "- 비슷한 내용을 다루는 후보는 하나로 합쳐서 한 항목으로만 다뤄.",
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


def _call_gemini(prompt: str, api_key: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    resp = _post_with_retry(
        url,
        params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
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
        },
    )
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _extractive_fallback(articles: list[Article], max_items: int) -> str:
    """LLM 두 곳 모두 실패했을 때의 최종 폴백: 규칙 기반 추출 + 무료 기계번역.

    품질은 LLM 요약보다 떨어지지만 API 키/비용 없이 100% 동작을 보장한다.
    """
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    header = f"*🌅 AI Morning Brief - {today}*\n(⚠️ 이 브리핑은 LLM 요약 없이 자동 생성되었습니다)"

    try:
        from deep_translator import GoogleTranslator

        translator = GoogleTranslator(source="auto", target="ko")
        translate = translator.translate
    except Exception as exc:  # noqa: BLE001
        print(f"[summarize] 번역기 초기화 실패, 원문 그대로 사용: {exc}")
        translate = None

    items = []
    for a in articles[:max_items]:
        title_ko = a.title
        snippet_ko = _clean_snippet(a.summary)[:200]
        if translate:
            try:
                title_ko = translate(a.title)
                if snippet_ko:
                    snippet_ko = translate(snippet_ko)
            except Exception as exc:  # noqa: BLE001
                print(f"[summarize] 번역 실패, 원문 유지: {exc}")
        items.append(f"🔹 *{title_ko}*\n{snippet_ko}\n\n출처: {a.source} | {a.link}")

    return header + "\n\n" + "\n\n".join(items)


def _articles_by_normalized_link(articles: list[Article], used_normalized: set[str]) -> list[Article]:
    return [a for a in articles if validate.normalize_link(a.link) in used_normalized]


def summarize_articles(articles: list[Article], settings: dict) -> tuple[str, str, list[Article]]:
    """반환값: (브리핑 텍스트, 사용된 티어 이름, 실제로 브리핑에 포함된 기사 목록)

    '포함된 기사 목록'은 이후 sent_history에 기록되어 다음 실행에서 같은 뉴스가
    다시 보내지지 않도록 하는 데 쓰인다. LLM 티어의 경우, 실제로 출력에 언급된
    (=검증을 통과한) 후보만 포함된 것으로 간주한다.
    """
    if not articles:
        today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
        return (
            f"*🌅 AI Morning Brief - {today}*\n오늘은 눈에 띄는 AI 뉴스가 없습니다.",
            "empty",
            [],
        )

    max_items = settings.get("pipeline", {}).get("max_items_in_brief", 8)
    limits = settings.get("usage_limits", {})
    state = usage_tracker.load()
    prompt = _build_prompt(articles, max_items)
    candidate_links = [a.link for a in articles]

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key and usage_tracker.under_soft_cap(
        state, "gemini", limits.get("gemini_daily_soft_cap", 20)
    ):
        gemini_text = None
        try:
            gemini_text = _call_gemini(prompt, gemini_key)
            usage_tracker.record_call(state, "gemini")
            usage_tracker.save(state)
        except Exception as exc:  # noqa: BLE001
            print(f"[summarize] Gemini 호출 실패, Groq으로 폴백: {exc}")
        if gemini_text is not None:
            valid, used_normalized = validate.validate_and_collect_used(gemini_text, candidate_links)
            if valid:
                return gemini_text, "gemini", _articles_by_normalized_link(articles, used_normalized)
            print("[summarize] Gemini 응답에 후보 목록에 없는 링크가 포함됨 - 검증 실패, Groq으로 폴백")

    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key and usage_tracker.under_soft_cap(
        state, "groq", limits.get("groq_daily_soft_cap", 20)
    ):
        groq_text = None
        try:
            groq_text = _call_groq(prompt, groq_key)
            usage_tracker.record_call(state, "groq")
            usage_tracker.save(state)
        except Exception as exc:  # noqa: BLE001
            print(f"[summarize] Groq 호출 실패, 규칙 기반 폴백으로 전환: {exc}")
        if groq_text is not None:
            valid, used_normalized = validate.validate_and_collect_used(groq_text, candidate_links)
            if valid:
                return groq_text, "groq", _articles_by_normalized_link(articles, used_normalized)
            print("[summarize] Groq 응답에 후보 목록에 없는 링크가 포함됨 - 검증 실패, 규칙 기반 폴백으로 전환")

    usage_tracker.save(state)
    included = articles[:max_items]
    return _extractive_fallback(articles, max_items), "fallback", included
