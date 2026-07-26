import time

import requests

HTTP_TIMEOUT = 15
MAX_RETRIES = 2


def _chunk_text(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at <= 0:
            split_at = max_len
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    return chunks


def _send_once(url: str, chat_id: str, text: str, use_markdown: bool) -> requests.Response:
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if use_markdown:
        payload["parse_mode"] = "Markdown"
    return requests.post(url, timeout=HTTP_TIMEOUT, json=payload)


def _is_entity_parse_error(resp: requests.Response) -> bool:
    if resp.status_code != 400:
        return False
    try:
        description = resp.json().get("description", "")
    except ValueError:
        description = resp.text
    return "can't parse entities" in description.lower()


def send_telegram(bot_token: str, chat_id: str, text: str, max_chars: int = 3900) -> None:
    """브리핑을 텔레그램으로 전송한다.

    parse_mode='Markdown'으로 먼저 시도하되, LLM 출력/번역 결과에 이스케이프되지 않은
    마크다운 특수문자(_,*,`,[)가 섞여 있어 텔레그램이 파싱에 실패하면(400 'can't parse
    entities'), 서식 없는 일반 텍스트로 즉시 재전송해 브리핑 자체는 반드시 도착하도록 한다.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = _chunk_text(text, max_chars)

    for i, chunk in enumerate(chunks, start=1):
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = _send_once(url, chat_id, chunk, use_markdown=True)
                if _is_entity_parse_error(resp):
                    print(
                        f"[notify] 마크다운 파싱 실패 ({i}/{len(chunks)}) - "
                        "서식 없는 일반 텍스트로 재전송합니다."
                    )
                    resp = _send_once(url, chat_id, chunk, use_markdown=False)
                resp.raise_for_status()
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                print(f"[notify] 텔레그램 전송 실패 ({i}/{len(chunks)}, 시도 {attempt}/{MAX_RETRIES}): {exc}")
                if attempt < MAX_RETRIES:
                    time.sleep(2)
        if last_exc:
            raise last_exc
