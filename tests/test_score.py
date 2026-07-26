import unittest
from datetime import datetime, timezone

from src import score
from src.models import Article


def make_article(title, summary="", weight=1.0):
    return Article(
        title=title,
        link=f"http://x/{hash(title)}",
        source="TestSource",
        source_weight=weight,
        published=datetime.now(timezone.utc),
        summary=summary,
    )


class TestFilterRelevant(unittest.TestCase):
    def test_excludes_articles_with_no_keyword_match(self):
        # 문제 2: 'Anthropic'이 회사가 아니라 철학 용어로 쓰인 것 같은,
        # AI 키워드가 전혀 없는 글은 후보에서 빠져야 한다.
        unrelated = make_article("인류는 목화를 따는 사회주의자들에게서 배워야 한다")
        relevant_article = make_article("OpenAI, 새로운 GPT 모델 공개")

        result = score.filter_relevant(
            [unrelated, relevant_article], high_keywords=["OpenAI", "GPT"], medium_keywords=[]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "OpenAI, 새로운 GPT 모델 공개")

    def test_medium_keyword_alone_is_enough_to_pass(self):
        article = make_article("A new model just launched", summary="")
        result = score.filter_relevant([article], high_keywords=[], medium_keywords=["launch"])
        self.assertEqual(len(result), 1)

    def test_keyword_match_in_summary_also_counts(self):
        article = make_article("제목에는 없음", summary="이 글은 Anthropic Claude에 대한 내용입니다")
        result = score.filter_relevant([article], high_keywords=["Anthropic"], medium_keywords=[])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
