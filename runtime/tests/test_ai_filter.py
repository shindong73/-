import json
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ai_filter


class AIGateTests(unittest.TestCase):
    def test_validation_of_complete_decisions(self):
        response = {
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps({
                    "items": [
                        {"id": "r", "approve": False, "reason": "정당 논평"},
                        {"id": "f", "approve": True, "reason": "정부 인사 변동"}
                    ]
                })}]
            }]
        }
        self.assertEqual(ai_filter.parse_decisions(response, ["r", "f"]),
                         {"r": False, "f": True})
        with self.assertRaises(ValueError):
            ai_filter.parse_decisions(response, ["r", "g"])
        with self.assertRaises(ValueError):
            ai_filter.parse_decisions({**response, "status": "incomplete"}, ["r", "f"])

    def test_post_batch_json_schema_no_raw_key_logging(self):
        news = [
            {"id": "r", "title": "국힘 최교진 사퇴 논평", "source": "KBS"},
            {"id": "f", "title": "최교진 교육부 장관 사의 표명", "source": "연합뉴스"}
        ]
        result = {"status": "completed", "output": [{
            "type": "message", "content": [{"type": "output_text", "text":
                json.dumps({"items":[
                    {"id":"r", "approve":False,"reason":"논평"},
                    {"id":"f", "approve":True,"reason":"사의"}
                ]})}]
        }]}
        class MockResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, n=-1): return json.dumps(result).encode("utf8")
        with patch.object(ai_filter, "urlopen", return_value=MockResponse()) as called:
            selection = ai_filter.screen_news(news, api_key="secret-for-test")
        self.assertEqual(selection, {"r":False,"f":True})
        request = called.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "gpt-5.6-luna")
        self.assertEqual(payload["store"], False)
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertNotIn("secret-for-test", request.data.decode())


if __name__ == "__main__":
    unittest.main()
