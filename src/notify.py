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


def send_telegram(bot_token: str, chat_id: str, text: str, max_chars: int = 3900) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = _chunk_text(text, max_chars)

    for i, chunk in enumerate(chunks, start=1):
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    url,
                    timeout=HTTP_TIMEOUT,
                    json={
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                )
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
