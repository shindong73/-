import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collector

NOW = datetime(2026, 11, 25, 0, 59, tzinfo=timezone.utc)
AI_SETTINGS = {
    "editorial_mode":"ai",
    "headline_max_age_minutes":90,
    "exclude_unfavorable_dem_news":True,
}

class AiFirstEditorialTests(unittest.TestCase):
    def test_ai_gets_verified_nonbreaking_headline_without_legacy_keywords(self):
        raw = """<rss><channel>
            <item><title>대통령실, 국정 과제 후속 조치 발표 - KBS 뉴스</title>
            <pubDate>Wed, 25 Nov 2026 00:58:00 GMT</pubDate>
            <link>https://news.google.com/rss/articles/ai-worthy</link>
            <source>KBS 뉴스</source></item>
        </channel></rss>"""
        with patch.object(collector, "get_url", return_value=raw.encode()):
            found=collector.fetch_rss("KBS",collector.NEWS_FEEDS["KBS"],NOW,AI_SETTINGS)
        self.assertEqual(len(found),1)
        self.assertFalse(collector.important_politics_news(found[0]["source_title"]))
        self.assertEqual(found[0]["kind"],"politics")
        self.assertEqual(found[0]["source"],"KBS")
        self.assertTrue(found[0]["caption_ready"])

    def test_ai_mode_never_bypasses_user_hard_exclusions(self):
        raw = """<rss><channel>
            <item><title>[단독] 정부, 국회 주요 인사 발표</title>
            <pubDate>Wed, 25 Nov 2026 00:58:00 GMT</pubDate>
            <link>https://news.google.com/rss/articles/exclusive</link><source>KBS 뉴스</source></item>
            <item><title>[속보] 선관위 직원 7명 구속</title>
            <pubDate>Wed, 25 Nov 2026 00:58:00 GMT</pubDate>
            <link>https://news.google.com/rss/articles/election</link><source>KBS 뉴스</source></item>
        </channel></rss>"""
        with patch.object(collector,"get_url",return_value=raw.encode()):
            self.assertEqual(collector.fetch_rss("KBS",collector.NEWS_FEEDS["KBS"],NOW,AI_SETTINGS),[])

    def _run(self,politics,*,api_key="test-key",decision=True):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            cfg=root/"config.json"
            cfg.write_text(json.dumps(AI_SETTINGS),encoding="utf8")
            state=root/"seen.json"
            state.write_text('{"initialized":true,"seen":{}}',encoding="utf8")
            payload=root/"payload.json"
            with patch.object(collector,"CONFIG_PATH",cfg), \
                 patch.object(collector,"STORE_PATH",state), \
                 patch.object(collector,"OUT_PATH",payload), \
                 patch.object(collector,"now_utc",return_value=NOW), \
                 patch.object(collector,"fetch_rss",return_value=politics), \
                 patch.dict(os.environ,{"GROQ_API_KEY":api_key}), \
                 patch.object(collector,"screen_news",return_value={x["id"]:decision for x in politics}) as model:
                result=collector.run("live")
                saved=json.loads(state.read_text(encoding="utf8"))
                return result,saved,model.call_args

    def test_only_ai_approved_political_event_is_published(self):
        article={
            "id":"ai-1","kind":"politics",
            "title":"대통령실이 국정 과제 후속 조치 발표",
            "source_title":"대통령실, 국정 과제 후속 조치 발표",
            "source":"KBS","published_at":collector.iso(NOW),
            "caption_ready":True,"is_test":False,
        }
        result,seen,args=self._run([article])
        self.assertEqual(len(result["items"]),1)
        self.assertIs(result["items"][0]["ai_approved"],True)
        self.assertEqual(args.kwargs["checked_at"],collector.iso(NOW))
        self.assertIn("ai-1",seen["seen"])

    def test_ai_rejection_is_consumed_and_never_published(self):
        article={
            "id":"party-opinion","kind":"politics",
            "title":"국민의힘 국정 논평",
            "source_title":'국힘 "정부 조치 유감"',
            "source":"KBS","published_at":collector.iso(NOW),
            "caption_ready":True,"is_test":False,
        }
        result,seen,_=self._run([article],decision=False)
        self.assertEqual(result["items"],[])
        self.assertIn("party-opinion",seen["seen"])

    def test_ai_mode_without_api_key_fails_closed(self):
        article={
            "id":"no-key","kind":"politics",
            "title":"대통령실이 국정 과제 후속 조치 발표",
            "source_title":"대통령실, 국정 과제 후속 조치 발표",
            "source":"KBS","published_at":collector.iso(NOW),
            "caption_ready":True,"is_test":False,
        }
        result,seen,model_args=self._run([article],api_key="")
        self.assertEqual(result["items"],[])
        self.assertIn("Groq API key missing",result["last_check_errors"][0])
        self.assertNotIn("no-key",seen["seen"])
        self.assertIsNone(model_args)



    def test_previous_gemini_cooldown_does_not_disable_new_groq(self):
        article = {
            "id": "new-provider", "kind": "politics",
            "title": "국회가 예산안 최종 가결",
            "source_title": "국회, 예산안 최종 가결",
            "source": "KBS", "published_at": collector.iso(NOW),
            "caption_ready": True, "is_test": False
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = root / "config.json"
            cfg.write_text(json.dumps(AI_SETTINGS), encoding="utf8")
            state_file = root / "seen.json"
            state_file.write_text(json.dumps({
                "initialized": True, "seen": {},
                "ai_next_attempt_at": collector.iso(NOW + collector.timedelta(hours=6)),
                "ai_last_http_status": 429
            }),encoding="utf8")
            payload = root / "payload.json"
            with patch.object(collector, "CONFIG_PATH", cfg), \
                 patch.object(collector, "STORE_PATH", state_file), \
                 patch.object(collector, "OUT_PATH", payload), \
                 patch.object(collector, "now_utc", return_value=NOW), \
                 patch.object(collector, "fetch_rss", return_value=[article]), \
                 patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), \
                 patch.object(collector, "screen_news", return_value={"new-provider": True}) as model:
                result = collector.run("live")
            self.assertEqual(model.call_count, 1)
            self.assertTrue(result["items"][0]["ai_approved"])
            new_state = json.loads(state_file.read_text(encoding="utf8"))
            self.assertEqual(new_state["ai_provider"], "groq")
            self.assertNotIn("ai_last_http_status", new_state)

    def test_ai_http_429_is_visible_and_rate_limited(self):
        article = {
            "id": "quota-test", "kind": "politics",
            "title": "정부가 중대 정책 조정 발표",
            "source_title": "정부, 중대 정책 조정 발표",
            "source": "KBS", "published_at": collector.iso(NOW),
            "caption_ready": True, "is_test": False,
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = root / "config.json"
            cfg.write_text(json.dumps(AI_SETTINGS), encoding="utf8")
            state_file = root / "seen.json"
            state_file.write_text('{"initialized":true,"seen":{}}', encoding="utf8")
            payload = root / "payload.json"
            with patch.object(collector, "CONFIG_PATH", cfg), \
                 patch.object(collector, "STORE_PATH", state_file), \
                 patch.object(collector, "OUT_PATH", payload), \
                 patch.object(collector, "now_utc", return_value=NOW), \
                 patch.object(collector, "fetch_rss", return_value=[article]), \
                 patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), \
                 patch.object(collector, "screen_news",
                     side_effect=HTTPError("https://example.com",429,"Too Many Requests",{},None)) as model:
                first = collector.run("live")
                self.assertEqual(model.call_count, 1)
                self.assertEqual(first["items"], [])
                self.assertIn("HTTP 429", first["last_check_errors"][0])
                persisted = json.loads(state_file.read_text(encoding="utf8"))
                self.assertEqual(persisted["ai_last_http_status"],429)
                self.assertTrue(persisted["ai_next_attempt_at"])
                with patch.object(collector,"now_utc",return_value=NOW+collector.timedelta(minutes=1)):
                    second = collector.run("live")
                self.assertEqual(model.call_count,1,
                                 "Cooldown must avoid hitting quota again")
                self.assertIn("HTTP 429",second["last_check_errors"][0])
                self.assertNotIn("quota-test",persisted["seen"])


    def test_free_fallback_delivers_major_event_without_api_key(self):
        article = {
            "id": "emergency-law-vote",
            "kind": "politics",
            "title": "국회가 주요 법안 가결",
            "source_title": "[속보] 국회, 주요 법안 가결",
            "source": "KBS",
            "published_at": collector.iso(NOW),
            "caption_ready": True,
            "is_test": False
        }
        result, state, model_args = self._run([article], api_key="")
        self.assertEqual(len(result["items"]), 1)
        self.assertIs(result["items"][0]["rules_fallback_approved"], True)
        self.assertIs(result["items"][0]["ai_approved"], False)
        self.assertIn("emergency-law-vote",state["seen"])
        self.assertIsNone(model_args)

    def test_fallback_blocks_commentary_old_news_and_unverified(self):
        base = {
            "id": "item", "kind": "politics",
            "source": "KBS", "caption_ready": True,
            "published_at": collector.iso(NOW), "is_test": False,
        }
        decision = collector.conservative_fallback_news
        self.assertFalse(decision({**base,
            "title": "정부 논평", "source_title": '국힘 "국회는 책임져야"'
        }, NOW), "party opinion must not pass emergency desk")
        self.assertFalse(decision({**base,
            "title": "국회가 예산안 가결", "source_title": "[단독] 국회, 예산안 가결"
        }, NOW), "exclusive user ban must be upheld")
        self.assertFalse(decision({**base,
            "title": "국회가 예산안 가결", "source_title": "선관위 국회 예산안 가결"
        }, NOW), "election topic ban must be upheld")
        self.assertFalse(decision({**base,
            "title": "국회가 예산안 가결", "source_title": "국회, 예산안 가결",
            "source": "USGS"
        }, NOW), "USGS must never be a fallback news source")
        self.assertFalse(decision({**base,
            "title": "국회가 예산안 가결", "source_title": "국회, 예산안 가결",
            "published_at": collector.iso(NOW - collector.timedelta(hours=2))
        }, NOW), "older articles cannot appear as urgent fallback news")
        self.assertFalse(decision({**base,
            "title": "국회가 예산안 가결", "source_title": "지난주 국회, 예산안 가결"
        }, NOW), "recaps must not appear as new breaking news")
        self.assertFalse(decision({**base,
            "title": "국회가 예산안 가결", "source_title": "국회, 예산안 가결",
            "caption_ready": False
        }, NOW), "verbatim or unsafe publisher titles never air")
        self.assertTrue(decision({**base,
            "title": "국회가 예산안 가결", "source_title": "[속보] 국회, 예산안 가결"
        }, NOW), "confirmed recent major decision should pass")

    def test_ai_explicit_rejection_cannot_be_overridden_by_fallback(self):
        article = {
            "id": "model-rejected",
            "kind": "politics",
            "title": "국회가 주요 법안 가결",
            "source_title": "국회, 주요 법안 가결",
            "source": "KBS",
            "published_at": collector.iso(NOW),
            "caption_ready": True,
            "is_test": False
        }
        result, state, model_args = self._run([article], decision=False)
        self.assertEqual(result["items"], [])
        self.assertIn("model-rejected",state["seen"])
        self.assertIsNotNone(model_args)

    def test_successful_ai_review_is_batched_and_throttled(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = root / "config.json"
            cfg.write_text(json.dumps(AI_SETTINGS),encoding="utf8")
            state_file=root / "seen.json"
            state_file.write_text('{"initialized":true,"seen":{}}',encoding="utf8")
            payload=root / "payload.json"
            articles=[
                {"id": f"event-{i}", "kind":"politics",
                 "title":"정부가 중대 정책 조정 발표",
                 "source_title":"정부, 중대 정책 조정 발표",
                 "source":"KBS",
                 "published_at":collector.iso(NOW),"caption_ready":True,"is_test":False}
                for i in range(15)
            ]
            with patch.object(collector,"CONFIG_PATH",cfg), \
                 patch.object(collector,"STORE_PATH",state_file), \
                 patch.object(collector,"OUT_PATH",payload), \
                 patch.object(collector,"now_utc",return_value=NOW), \
                 patch.object(collector,"fetch_rss",return_value=articles), \
                 patch.dict(os.environ,{"GROQ_API_KEY":"test-key"}), \
                 patch.object(collector,"screen_news",return_value={}) as model:
                first=collector.run("live")
                self.assertEqual(len(model.call_args.args[0]),8)
                self.assertEqual(first["items"],[])
                with patch.object(collector,"now_utc",return_value=NOW+collector.timedelta(minutes=1)):
                    collector.run("live")
                self.assertEqual(model.call_count,1)

if __name__ == "__main__":
    unittest.main()
