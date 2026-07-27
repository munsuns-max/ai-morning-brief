import unittest

from src import validate


class TestValidateItems(unittest.TestCase):
    def test_valid_when_all_item_links_are_known_candidates(self):
        items = [{"title": "제목", "summary": "요약", "link": "https://a.com/story"}]
        ok, validated = validate.validate_items(items, ["https://a.com/story"])
        self.assertTrue(ok)
        self.assertEqual(validated, items)

    def test_invalid_when_llm_invents_a_link_not_in_candidates(self):
        # 후보 목록에 없는 링크가 섞여 있으면 검증 실패로 처리해야 한다.
        items = [{"title": "지어낸 뉴스", "summary": "요약", "link": "https://not-a-real-candidate.com/fake"}]
        ok, validated = validate.validate_items(items, ["https://a.com/story"])
        self.assertFalse(ok)
        self.assertEqual(validated, [])

    def test_invalid_when_only_some_items_have_unknown_links(self):
        items = [
            {"title": "진짜 뉴스", "summary": "요약", "link": "https://a.com/story"},
            {"title": "지어낸 뉴스", "summary": "요약", "link": "https://fake.com/made-up"},
        ]
        ok, validated = validate.validate_items(items, ["https://a.com/story"])
        self.assertFalse(ok)

    def test_tolerates_scheme_and_trailing_slash_differences(self):
        items = [{"title": "제목", "summary": "요약", "link": "http://a.com/story/"}]
        ok, validated = validate.validate_items(items, ["https://a.com/story"])
        self.assertTrue(ok)

    def test_empty_items_list_is_valid(self):
        ok, validated = validate.validate_items([], ["https://a.com/story"])
        self.assertTrue(ok)
        self.assertEqual(validated, [])


if __name__ == "__main__":
    unittest.main()
