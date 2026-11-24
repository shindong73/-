import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
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
                 patch.dict(os.environ,{"GEMINI_API_KEY":api_key}), \
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
        self.assertIn("Gemini API key missing",result["last_check_errors"][0])
        self.assertNotIn("no-key",seen["seen"])
        self.assertIsNone(model_args)

if __name__ == "__main__":
    unittest.main()
