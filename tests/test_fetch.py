import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from src.fetch import _parse_published, fetch_feed


class FakeParsed:
    def __init__(self, entries, bozo=False):
        self.entries = entries
        self.bozo = bozo


class TestParsePublished(unittest.TestCase):
    def test_missing_date_returns_none(self):
        # 문제 4: 발행일이 없으면 '최신'으로 간주해선 안 되고 None(=제외 대상)이어야 한다.
        entry = SimpleNamespace(title="t", link="l", summary="s")
        self.assertIsNone(_parse_published(entry))

    def test_present_published_date_is_parsed_correctly(self):
        struct = time.gmtime(0)  # 1970-01-01
        entry = SimpleNamespace(published_parsed=struct)
        result = _parse_published(entry)
        self.assertEqual(result, datetime(1970, 1, 1, tzinfo=timezone.utc))

    def test_falls_back_to_updated_parsed(self):
        struct = time.gmtime(0)
        entry = SimpleNamespace(updated_parsed=struct)
        result = _parse_published(entry)
        self.assertEqual(result, datetime(1970, 1, 1, tzinfo=timezone.utc))


class TestFetchFeedSkipsUndatedEntries(unittest.TestCase):
    @patch("src.fetch.feedparser.parse")
    def test_entries_without_any_date_are_excluded(self, mock_parse):
        entries = [
            SimpleNamespace(title="날짜 없는 오래된 글", link="https://example.com/a", summary="s"),
            SimpleNamespace(
                title="날짜 있는 최신 글",
                link="https://example.com/b",
                summary="s",
                published_parsed=time.gmtime(),
            ),
        ]
        mock_parse.return_value = FakeParsed(entries)

        articles = fetch_feed("TestSource", "http://feed.url", weight=1)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "날짜 있는 최신 글")


if __name__ == "__main__":
    unittest.main()
