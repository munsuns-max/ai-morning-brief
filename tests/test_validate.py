import unittest

from src import validate


class TestValidateAndCollectUsed(unittest.TestCase):
    def test_valid_when_all_mentioned_links_are_known_candidates(self):
        text = "- *제목* 요약 내용입니다. (출처: A, https://a.com/story)"
        ok, used = validate.validate_and_collect_used(text, ["https://a.com/story"])
        self.assertTrue(ok)
        self.assertIn(validate.normalize_link("https://a.com/story"), used)

    def test_invalid_when_llm_invents_a_link_not_in_candidates(self):
        # 문제 5: 후보 목록에 없는 링크가 섞여 있으면 검증 실패로 처리해야 한다.
        text = "- *지어낸 뉴스* 요약. (출처: 알수없음, https://not-a-real-candidate.com/fake)"
        ok, used = validate.validate_and_collect_used(text, ["https://a.com/story"])
        self.assertFalse(ok)
        self.assertEqual(used, set())

    def test_invalid_when_only_some_links_are_unknown(self):
        text = (
            "- *진짜 뉴스* (출처: A, https://a.com/story)\n"
            "- *지어낸 뉴스* (출처: B, https://fake.com/made-up)"
        )
        ok, used = validate.validate_and_collect_used(text, ["https://a.com/story"])
        self.assertFalse(ok)

    def test_tolerates_scheme_and_trailing_slash_differences(self):
        text = "(출처: A, http://a.com/story/)"
        ok, used = validate.validate_and_collect_used(text, ["https://a.com/story"])
        self.assertTrue(ok)

    def test_no_links_mentioned_is_valid_with_empty_used_set(self):
        text = "오늘은 특별히 다룰 소식이 없습니다."
        ok, used = validate.validate_and_collect_used(text, ["https://a.com/story"])
        self.assertTrue(ok)
        self.assertEqual(used, set())


if __name__ == "__main__":
    unittest.main()
