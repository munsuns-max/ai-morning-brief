import unittest
from datetime import datetime, timedelta, timezone

from src import sent_history
from src.models import Article


def make_article(title, link):
    return Article(
        title=title,
        link=link,
        source="TestSource",
        source_weight=1.0,
        published=datetime.now(timezone.utc),
    )


class TestFilterUnsent(unittest.TestCase):
    def test_excludes_exact_link_already_sent(self):
        # 문제 3: 링크가 완전히 같은 기사는 재전송하지 않는다.
        history = [
            {"link": "http://x/1", "title": "Old title", "sent_at": datetime.now(timezone.utc).isoformat()}
        ]
        articles = [make_article("New title", "http://x/1"), make_article("Another", "http://x/2")]

        result = sent_history.filter_unsent(articles, history, similarity_threshold=78)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].link, "http://x/2")

    def test_excludes_near_duplicate_title_even_with_different_link(self):
        # lookback 겹침 구간 때문에 같은 기사가 다른 URL(예: 파라미터 차이)로 다시
        # 잡혀도 제목 유사도로 잡아내야 한다.
        history = [
            {
                "link": "http://old-url",
                "title": "OpenAI releases GPT-5 today",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        articles = [make_article("OpenAI releases GPT-5 today!!", "http://new-different-url")]

        result = sent_history.filter_unsent(articles, history, similarity_threshold=78)

        self.assertEqual(len(result), 0)

    def test_genuinely_different_article_is_kept(self):
        history = [
            {
                "link": "http://old-url",
                "title": "OpenAI releases GPT-5",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        articles = [make_article("Anthropic announces new safety research", "http://new-url")]

        result = sent_history.filter_unsent(articles, history, similarity_threshold=78)

        self.assertEqual(len(result), 1)


class TestPrune(unittest.TestCase):
    def test_removes_entries_older_than_retention(self):
        old = {
            "link": "a",
            "title": "a",
            "sent_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        }
        recent = {"link": "b", "title": "b", "sent_at": datetime.now(timezone.utc).isoformat()}

        result = sent_history.prune([old, recent])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["link"], "b")

    def test_malformed_entries_are_dropped_not_crashed_on(self):
        malformed = {"link": "a"}  # sent_at 없음
        recent = {"link": "b", "title": "b", "sent_at": datetime.now(timezone.utc).isoformat()}

        result = sent_history.prune([malformed, recent])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["link"], "b")


if __name__ == "__main__":
    unittest.main()
