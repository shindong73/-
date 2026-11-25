import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ai_filter


class MockResponse:
    def __init__(self, body):
        self.body = json.dumps(body, ensure_ascii=False).encode("utf8")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, n=-1):
        return self.body if n == -1 else self.body[:n]


class GroqEditorialTests(unittest.TestCase):
    def test_decision_schema_validation(self):
        rows = [
            {"id": "a", "approve": False, "reason": "정당 논평"},
            {"id": "b", "approve": True, "reason": "확정 인사"},
        ]
        self.assertEqual(
            ai_filter.validate_decision_rows(rows, ["a", "b"]),
            {"a": False, "b": True}
        )
        bad = [
            rows[:1],
            rows + rows,
            [{"id": "a", "approve": "true", "reason": "문제"}],
            [{"id": "not-requested", "approve": True, "reason": "문제"},
             {"id": "a", "approve": False, "reason": "문제"}]
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ai_filter.validate_decision_rows(value, ["a", "b"])

    def test_free_groq_request_and_strict_json(self):
        articles = [
            {"id": "a", "title": "방송용 요약",
             "source_title": '국힘 "최교진 사퇴로 끝날 일 아냐"',
             "published_at": "2026-11-25T10:59:00Z", "source": "KBS"},
            {"id": "b", "title": "최교진 사의 발표",
             "source_title": "최교진 교육부 장관 사의 표명",
             "published_at": "2026-11-25T11:00:00Z", "source": "연합뉴스"}
        ]
        rows = [
            {"id": "a", "approve": False, "reason": "논평"},
            {"id": "b", "approve": True, "reason": "공식 사의"}
        ]
        response = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({"items": rows}, ensure_ascii=False)}
            }]
        }
        with patch.object(ai_filter, "urlopen", return_value=MockResponse(response)) as called:
            decisions = ai_filter.screen_news_groq(
                articles, api_key="secret-test", checked_at="2026-11-25T11:00:00Z"
            )
        self.assertEqual(decisions, {"a": False, "b": True})
        req = called.call_args.args[0]
        self.assertEqual(req.full_url, ai_filter.GROQ_ENDPOINT)
        self.assertEqual(req.get_header("Authorization"), "Bearer secret-test")
        body = json.loads(req.data)
        self.assertEqual(body["model"], "openai/gpt-oss-20b")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertFalse(body["response_format"]["json_schema"]["schema"]["additionalProperties"])
        self.assertEqual(body["messages"][0]["role"], "system")
        requested = json.loads(body["messages"][1]["content"])
        self.assertEqual(requested["articles"][0]["title"], articles[0]["source_title"])
        self.assertEqual(requested["checked_at_utc"], "2026-11-25T11:00:00Z")
        self.assertNotIn("secret-test", req.data.decode("utf8"))

    def test_missing_key_bad_model_and_oversized_batch(self):
        self.assertEqual(ai_filter.screen_news_groq([], api_key=""), {})
        with self.assertRaises(ValueError):
            ai_filter.screen_news_groq([{"id": "a"}], api_key="")
        with self.assertRaises(ValueError):
            ai_filter.screen_news_groq(
                [{"id": "a", "title": "뉴스", "source": "KBS"}],
                api_key="x", model="../../bad"
            )
        with self.assertRaises(ValueError):
            ai_filter.screen_news_groq(
                [{"id": str(i)} for i in range(9)],
                api_key="x"
            )

    def test_incomplete_api_response_is_never_approved(self):
        article = [{"id": "a", "title": "기사", "source": "KBS"}]
        invalid = [
            {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
            {"choices": []},
            {"choices": [{"finish_reason": "stop", "message": {"content": '{"items":[]}'}}]}
        ]
        for response in invalid:
            with self.subTest(response=response), patch.object(
                ai_filter, "urlopen", return_value=MockResponse(response)
            ), self.assertRaises(ValueError):
                ai_filter.screen_news_groq(article, api_key="x")


if __name__ == "__main__":
    unittest.main()
