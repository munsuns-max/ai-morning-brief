import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from src.models import Article
from src.summarize import _build_prompt, summarize_articles

# 테스트가 실제 운영 상태 파일(state/usage.json)에 부작용을 남기지 않도록,
# usage_tracker가 쓰는 파일 경로를 임시 파일로 바꿔치기한다.
_TEST_USAGE_FILE = os.path.join(tempfile.gettempdir(), "ai_news_test_usage.json")


def make_article(i, summary="Summary text"):
    return Article(
        title=f"Title {i}",
        link=f"http://x/{i}",
        source="TestSource",
        source_weight=1.0,
        published=datetime.now(timezone.utc),
        summary=summary,
    )


class TestPromptScalesWithCandidateCount(unittest.TestCase):
    def test_prompt_asks_for_exact_count_when_few_candidates(self):
        # 문제 1: 후보가 2개뿐이면 "5~8개를 채워라"가 아니라 "최대 2개"라고 지시해야 한다.
        articles = [make_article(1), make_article(2)]
        prompt = _build_prompt(articles, max_items_in_brief=8)
        self.assertIn("최대 2개", prompt)
        self.assertNotIn("5~8개", prompt)

    def test_prompt_caps_at_configured_max_when_many_candidates(self):
        articles = [make_article(i) for i in range(20)]
        prompt = _build_prompt(articles, max_items_in_brief=8)
        self.assertIn("최대 8개", prompt)

    def test_prompt_explicitly_forbids_padding(self):
        articles = [make_article(1)]
        prompt = _build_prompt(articles, max_items_in_brief=8)
        self.assertIn("억지로", prompt)


class TestSummarizeArticlesFallbackBehaviour(unittest.TestCase):
    @mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": ""})
    @mock.patch("deep_translator.GoogleTranslator")
    def test_no_api_keys_uses_rule_based_fallback_with_only_real_articles(self, mock_translator_cls):
        mock_translator_cls.return_value.translate.side_effect = lambda t: t  # 번역 통과(네트워크 미사용)

        articles = [make_article(1), make_article(2), make_article(3)]
        settings = {"pipeline": {"max_items_in_brief": 8}, "usage_limits": {}}

        text, tier, included = summarize_articles(articles, settings)

        self.assertEqual(tier, "fallback")
        self.assertEqual(len(included), 3)
        # 실제로 수집된 기사의 링크만 브리핑에 등장해야 한다 (지어낸 내용 없음).
        for a in articles:
            self.assertIn(a.link, text)

    def test_empty_candidate_list_returns_no_news_message_and_no_included_articles(self):
        settings = {"pipeline": {"max_items_in_brief": 8}, "usage_limits": {}}
        text, tier, included = summarize_articles([], settings)
        self.assertEqual(tier, "empty")
        self.assertEqual(included, [])
        self.assertIn("없습니다", text)

    @mock.patch("src.usage_tracker.USAGE_FILE", _TEST_USAGE_FILE)
    @mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": ""})
    @mock.patch("src.summarize._call_gemini")
    @mock.patch("deep_translator.GoogleTranslator")
    def test_gemini_response_with_fabricated_link_is_rejected_and_falls_back(
        self, mock_translator_cls, mock_call_gemini
    ):
        # 문제 5: Gemini가 후보에 없는 링크를 지어내면 그 응답은 버려지고
        # 규칙 기반 폴백으로 전환되어야 한다.
        mock_translator_cls.return_value.translate.side_effect = lambda t: t
        mock_call_gemini.return_value = (
            "- *지어낸 뉴스* 요약. (출처: 없음, https://this-link-does-not-exist.example.com/fake)"
        )

        articles = [make_article(1)]
        settings = {"pipeline": {"max_items_in_brief": 8}, "usage_limits": {}}

        text, tier, included = summarize_articles(articles, settings)

        self.assertEqual(tier, "fallback")
        self.assertNotIn("this-link-does-not-exist.example.com", text)
        self.assertIn(articles[0].link, text)

    @mock.patch("src.usage_tracker.USAGE_FILE", _TEST_USAGE_FILE)
    @mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": ""})
    @mock.patch("src.summarize._call_gemini")
    def test_gemini_response_with_only_known_links_is_accepted(self, mock_call_gemini):
        articles = [make_article(1), make_article(2)]
        mock_call_gemini.return_value = (
            f"- *뉴스1* 요약. (출처: A, {articles[0].link})\n"
            f"- *뉴스2* 요약. (출처: B, {articles[1].link})"
        )
        settings = {"pipeline": {"max_items_in_brief": 8}, "usage_limits": {}}

        text, tier, included = summarize_articles(articles, settings)

        self.assertEqual(tier, "gemini")
        self.assertEqual({a.link for a in included}, {articles[0].link, articles[1].link})


if __name__ == "__main__":
    unittest.main()
