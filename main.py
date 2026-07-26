import os
import sys

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src import notify, score, sent_history
from src.dedupe import dedupe
from src.fetch import fetch_all
from src.summarize import summarize_articles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_yaml(relative_path: str) -> dict:
    with open(os.path.join(BASE_DIR, relative_path), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    dry_run = os.environ.get("DRY_RUN") == "1"
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not dry_run and (not bot_token or not chat_id):
        print("[main] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수가 필요합니다.")
        return 1

    feeds_config = load_yaml("config/feeds.yaml")["feeds"]
    settings = load_yaml("config/settings.yaml")
    pipeline_cfg = settings["pipeline"]
    keywords_cfg = settings["keywords"]

    history = sent_history.load()
    history = sent_history.prune(history)

    articles = fetch_all(feeds_config, pipeline_cfg["lookback_hours"])
    print(f"[main] 전체 수집(발행일 확인된 것만): {len(articles)}건")

    relevant = score.filter_relevant(articles, keywords_cfg["high"], keywords_cfg["medium"])
    print(f"[main] AI 관련 키워드 매칭 통과: {len(relevant)}건 (제외: {len(articles) - len(relevant)}건)")

    unsent = sent_history.filter_unsent(
        relevant, history, pipeline_cfg["dedupe_similarity_threshold"]
    )
    print(f"[main] 이미 전송된 뉴스 제외 후: {len(unsent)}건 (제외: {len(relevant) - len(unsent)}건)")

    clustered = dedupe(unsent, pipeline_cfg["dedupe_similarity_threshold"])
    print(f"[main] 중복 제거 후: {len(clustered)}건")
    if not clustered:
        print("[main] 후보가 없어 '뉴스 없음' 브리핑을 전송합니다.")

    ranked = score.score_articles(
        clustered,
        keywords_cfg["high"],
        keywords_cfg["medium"],
        pipeline_cfg["lookback_hours"],
    )

    top_candidates = ranked[: pipeline_cfg["max_candidates_for_llm"]]
    print(f"[main] LLM에 전달할 후보: {len(top_candidates)}건")

    brief_text, tier, included_articles = summarize_articles(top_candidates, settings)
    print(f"[main] 요약에 사용된 티어: {tier}, 실제 브리핑에 포함된 기사: {len(included_articles)}건")

    if dry_run:
        print("\n===== DRY RUN: 텔레그램 전송 없이 브리핑만 출력합니다 (sent_history는 갱신하지 않음) =====\n")
        print(brief_text)
        return 0

    notify.send_telegram(bot_token, chat_id, brief_text, pipeline_cfg["telegram_max_chars"])
    print("[main] 텔레그램 전송 완료")

    if included_articles:
        history = sent_history.record_sent(history, included_articles)
        sent_history.save(history)
        print(f"[main] sent_history 갱신: {len(included_articles)}건 기록")

    return 0


if __name__ == "__main__":
    sys.exit(main())
