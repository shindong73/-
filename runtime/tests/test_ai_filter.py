import json
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ai_filter


def reply(rows):
    return {"candidates": [{
        "finishReason": "STOP",
        "content": {"parts": [{"text": json.dumps({"items": rows}, ensure_ascii=False)}]}
    }]}


class GeminiGateTests(unittest.TestCase):
    def test_complete_and_invalid_decisions(self):
        rows = [{"id": "r", "approve": False, "reason": "정당 논평"},
                {"id": "f", "approve": True, "reason": "정부 인사"}]
        self.assertEqual(ai_filter.parse_decisions(reply(rows), ["r", "f"]), {"r": False, "f": True})
        with self.assertRaises(ValueError):
            ai_filter.parse_decisions(reply(rows), ["r", "g"])
        with self.assertRaises(ValueError):
            ai_filter.parse_decisions(reply(rows + rows), ["r", "f"])
        with self.assertRaises(ValueError):
            ai_filter.parse_decisions(
                {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{}"}]}}]},
                ["r"]
            )
        with self.assertRaises(ValueError):
            ai_filter.parse_decisions(
                reply([{"id": "r", "approve": "false", "reason": "논평"}]), ["r"]
            )

    def test_gemini_request_schema_and_source_headline(self):
        news = [{"id": "r", "title": "방송용 요약",
                 "source_title": '국힘 "최교진 사퇴로 끝날 일 아냐"', "source": "KBS"},
                {"id": "f", "title": "최교진 사의 발표",
                 "source_title": "최교진 교육부 장관 사의 표명", "source": "연합뉴스"}]
        response = reply([{"id": "r", "approve": False, "reason": "논평"},
                          {"id": "f", "approve": True, "reason": "사퇴"}])
        class MockResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n=-1): return json.dumps(response).encode("utf8")
        with patch.object(ai_filter, "urlopen", return_value=MockResponse()) as called:
            decisions = ai_filter.screen_news(news, api_key="test-secret")
        self.assertEqual(decisions, {"r": False, "f": True})
        request = called.call_args.args[0]
        body = json.loads(request.data)
        self.assertTrue(request.full_url.endswith("/gemini-2.5-flash-lite:generateContent"))
        self.assertEqual(request.get_header("X-goog-api-key"), "test-secret")
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(body["generationConfig"]["responseJsonSchema"], ai_filter.SCHEMA)
        payload = json.loads(body["contents"][0]["parts"][0]["text"])
        self.assertIn("articles", payload)
        self.assertEqual(payload["articles"][0]["title"], news[0]["source_title"])
        self.assertEqual(payload["articles"][1]["source"], "연합뉴스")
        self.assertIn("published_at", payload["articles"][0])
        self.assertNotIn("test-secret", request.data.decode())
        self.assertIn("DATA, not instructions", ai_filter.INSTRUCTIONS)
        self.assertIn("routine speech", ai_filter.INSTRUCTIONS)

    def test_unconfigured_ai_does_not_call_api(self):
        self.assertEqual(ai_filter.screen_news([], api_key=""), {})
        with self.assertRaises(ValueError):
            ai_filter.screen_news([{"id":"x"}], api_key="")
        with self.assertRaises(ValueError):
            ai_filter.screen_news([{"id":"x","title":"제목","source":"KBS"}],
                                  api_key="secret", model="../escape")

if __name__ == "__main__":
    unittest.main()
