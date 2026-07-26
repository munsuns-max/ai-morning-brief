import unittest
from unittest.mock import patch

from src.notify import _chunk_text, send_telegram


class FakeResponse:
    def __init__(self, status_code=200, description=""):
        self.status_code = status_code
        self._description = description
        self.text = description

    def json(self):
        return {"ok": self.status_code == 200, "description": self._description}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"{self.status_code}: {self._description}")


class TestChunkText(unittest.TestCase):
    def test_short_text_is_a_single_chunk(self):
        self.assertEqual(_chunk_text("hello", 100), ["hello"])

    def test_long_text_splits_on_newline_boundary(self):
        text = "a" * 50 + "\n" + "b" * 50
        chunks = _chunk_text(text, max_len=60)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(c) <= 60 for c in chunks))


class TestSendTelegramMarkdownFallback(unittest.TestCase):
    @patch("src.notify.requests.post")
    def test_successful_markdown_send_does_not_retry(self, mock_post):
        mock_post.return_value = FakeResponse(status_code=200)

        send_telegram("token", "chat123", "*정상 메시지*")

        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_post.call_args.kwargs["json"]["parse_mode"], "Markdown")

    @patch("src.notify.requests.post")
    def test_entity_parse_failure_falls_back_to_plain_text_and_succeeds(self, mock_post):
        # 문제 A: 마크다운 파싱 실패(400 can't parse entities) 시, 서식 없이
        # 재전송해서라도 브리핑이 실제로 도착해야 한다.
        mock_post.side_effect = [
            FakeResponse(status_code=400, description="Bad Request: can't parse entities: ..."),
            FakeResponse(status_code=200),
        ]

        send_telegram("token", "chat123", "GPT_4 모델과 state_dict 관련 소식")

        self.assertEqual(mock_post.call_count, 2)
        first_payload = mock_post.call_args_list[0].kwargs["json"]
        second_payload = mock_post.call_args_list[1].kwargs["json"]
        self.assertEqual(first_payload.get("parse_mode"), "Markdown")
        self.assertNotIn("parse_mode", second_payload)

    @patch("src.notify.requests.post")
    def test_non_entity_400_error_is_not_retried_as_plain_text(self, mock_post):
        # chat_id가 잘못된 것처럼 마크다운과 무관한 400 에러는 그대로 실패해야 한다
        # (마크다운 폴백으로 재시도해봐야 소용없으므로).
        mock_post.return_value = FakeResponse(status_code=400, description="Bad Request: chat not found")

        with self.assertRaises(Exception):
            send_telegram("token", "wrong-chat", "메시지")

        # 두 번의 재시도(MAX_RETRIES=2) 모두 동일하게 markdown으로 시도했어야 한다.
        for call in mock_post.call_args_list:
            self.assertEqual(call.kwargs["json"].get("parse_mode"), "Markdown")


if __name__ == "__main__":
    unittest.main()
