import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import requests

from src.fetch import _parse_published, fetch_feed


class FakeParsed:
    def __init__(self, entries, bozo=False):
        self.entries = entries
        self.bozo = bozo


class FakeResponse:
    def __init__(self, content=b"", status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")


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
    @patch("src.fetch.requests.get")
    def test_entries_without_any_date_are_excluded(self, mock_get, mock_parse):
        mock_get.return_value = FakeResponse(content=b"<rss></rss>")
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


class TestFetchFeedNetworkFailures(unittest.TestCase):
    """문제 B: 피드 요청에 실제 타임아웃이 걸려 있고, 하나가 죽어도 예외 없이
    빈 목록을 반환해 전체 파이프라인이 계속 진행될 수 있어야 한다."""

    @patch("src.fetch.requests.get")
    def test_timeout_returns_empty_list_without_raising(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("timed out")

        articles = fetch_feed("SlowSource", "http://slow.feed.url", weight=1)

        self.assertEqual(articles, [])

    @patch("src.fetch.requests.get")
    def test_get_is_called_with_a_timeout_argument(self, mock_get):
        mock_get.return_value = FakeResponse(content=b"<rss></rss>")

        fetch_feed("TestSource", "http://feed.url", weight=1)

        _, kwargs = mock_get.call_args
        self.assertIn("timeout", kwargs)
        self.assertGreater(kwargs["timeout"], 0)

    @patch("src.fetch.requests.get")
    def test_http_error_status_returns_empty_list_without_raising(self, mock_get):
        mock_get.return_value = FakeResponse(status_code=403)

        articles = fetch_feed("BlockedSource", "http://blocked.feed.url", weight=1)

        self.assertEqual(articles, [])


if __name__ == "__main__":
    unittest.main()
