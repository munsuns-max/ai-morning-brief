import json
import os
from datetime import date

USAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state", "usage.json")


def _today_key() -> str:
    return date.today().isoformat()


def _month_key() -> str:
    return date.today().strftime("%Y-%m")


def load() -> dict:
    if not os.path.exists(USAGE_FILE):
        return {}
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(state: dict) -> None:
    os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_today_count(state: dict, provider: str) -> int:
    day = state.get(provider, {}).get("day")
    if day != _today_key():
        return 0
    return state.get(provider, {}).get("count", 0)


def record_call(state: dict, provider: str) -> dict:
    today = _today_key()
    entry = state.get(provider, {})
    if entry.get("day") != today:
        entry = {"day": today, "count": 0}
    entry["count"] += 1
    state[provider] = entry
    state["month"] = _month_key()
    return state


def under_soft_cap(state: dict, provider: str, soft_cap: int) -> bool:
    count = get_today_count(state, provider)
    if count >= soft_cap:
        print(f"[usage] '{provider}' 일일 소프트 캡({soft_cap}회) 도달 - 다음 폴백 단계로 전환합니다.")
        return False
    return True
