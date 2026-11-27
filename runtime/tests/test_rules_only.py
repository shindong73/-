"""Regression tests for the zero-API, multi-stage news editorial desk."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collector

T = datetime(2026, 11, 25, 11, 0, tzinfo=timezone.utc)

class RulesOnlyDeskTests(unittest.TestCase):
    def test_confirmed_major_events_have_ranked_priority(self):
        self.assertGreaterEqual(collector.headline_priority(
            "[속보] 국회, 주요 법안 가결"), 80)
        self.assertGreaterEqual(collector.headline_priority(
            "[긴급] 최교진 교육부 장관 사의 표명"), 90)
        self.assertGreaterEqual(collector.headline_priority(
            "헌재, 주요 사건 최종 선고"), 80)
        self.assertGreaterEqual(collector.headline_priority(
            "검찰, 국가 중요 사건 관련자 구속"), 70)

    def test_breaking_badge_alone_is_not_news(self):
        headlines = (
            "[속보] 이재명 대통령 전통시장 방문",
            "[속보] 국회 토론회 참석",
            "[속보] 정부 주요 현안 논의",
            "국민의힘, 정부를 향해 비판 쏟아내",
            '[속보] 국힘 "수능마저 못 믿는 나라…최교진 사퇴로 끝날 일 아냐"',
            "[속보] 장관 사퇴 요구",
            "[속보] 국정원장 교체설",
            "[속보] 국회 예산안 처리 가능성",
            "[속보] 국회 예산안 처리 전망",
            "[속보] 국회 예산안 처리 검토",
        )
        for title in headlines:
            with self.subTest(title=title):
                self.assertEqual(collector.headline_priority(title),0)

    def test_explicit_topic_bans_and_recaps_are_not_replayed(self):
        headlines = (
            "[속보] 선관위 직원 7명 구속",
            "[단독] 국회 예산안 최종 가결",
            "국회 부정선거 의혹 수사 결론",
            "미국 국회 주요 법안 가결",
            "북한 미사일 대응 국회 의결",
            "지난주 국회 예산안 최종 가결",
            "어제 국회 예산안 최종 가결",
            "울산시, 이경식 울산경제자유구역청장 해임",
        )
        for title in headlines:
            with self.subTest(title=title):
                self.assertEqual(collector.headline_priority(title),0)

    def test_rss_stages_reject_opinion_but_keep_confirmed_event(self):
        raw = """<rss><channel>
            <item><title>[속보] 국회, 주요 법안 가결</title>
            <pubDate>Wed, 25 Nov 2026 10:59:00 GMT</pubDate>
            <link>https://news.google.com/rss/articles/1</link><source>KBS 뉴스</source></item>
            <item><title>[속보] 국회 행사 참석</title>
            <pubDate>Wed, 25 Nov 2026 10:59:00 GMT</pubDate>
            <link>https://news.google.com/rss/articles/2</link><source>KBS 뉴스</source></item>
            <item><title>[단독] 국회 예산안 최종 가결</title>
            <pubDate>Wed, 25 Nov 2026 10:59:00 GMT</pubDate>
            <link>https://news.google.com/rss/articles/3</link><source>KBS 뉴스</source></item>
            <item><title>[속보] 국회 예산안 가결</title>
            <pubDate>Tue, 24 Nov 2026 08:00:00 GMT</pubDate>
            <link>https://news.google.com/rss/articles/4</link><source>KBS 뉴스</source></item>
        </channel></rss>"""
        settings = {
            "headline_max_age_minutes": 90,
            "exclude_unfavorable_dem_news": True
        }
        with patch.object(collector, "get_url", return_value=raw.encode("utf8")):
            found = collector.fetch_rss("KBS",collector.NEWS_FEEDS["KBS"],T,settings)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["title"],"국회서 주요 법안 가결")
        self.assertGreater(found[0]["priority"],0)

    def test_old_provider_cooldown_removed_and_rules_run_without_keys(self):
        article = {
            "id": "rules-national-vote", "kind": "politics",
            "title": "국회가 주요 법안 가결",
            "source_title": "[속보] 국회, 주요 법안 가결",
            "source": "KBS", "published_at": collector.iso(T),
            "caption_ready": True, "is_test": False
        }
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cfg=root/"config.json"
            cfg.write_text(json.dumps({
                "headline_max_age_minutes":90,
                "max_news_per_run":3
            }),encoding="utf8")
            state_file=root/"seen.json"
            state_file.write_text(json.dumps({
                "initialized":True, "seen":{},
                "ai_provider":"groq",
                "ai_next_attempt_at":collector.iso(T+collector.timedelta(days=30)),
                "ai_last_http_status":429
            }),encoding="utf8")
            out=root/"feed.json"
            with patch.object(collector,"CONFIG_PATH",cfg), \
                 patch.object(collector,"STORE_PATH",state_file), \
                 patch.object(collector,"OUT_PATH",out), \
                 patch.object(collector,"now_utc",return_value=T), \
                 patch.object(collector,"fetch_rss",return_value=[article]):
                data=collector.run("live")
            self.assertEqual([x["id"] for x in data["items"]],["rules-national-vote"])
            self.assertTrue(data["items"][0]["rules_approved"])
            self.assertNotIn("ai_approved",data["items"][0])
            self.assertNotIn("ai_provider",json.loads(state_file.read_text(encoding="utf8")))
            self.assertNotIn("ai_next_attempt_at",json.loads(state_file.read_text(encoding="utf8")))
            self.assertEqual(data["last_check_errors"], [])

    def test_no_model_network_dependencies(self):
        source=Path(collector.__file__).read_text(encoding="utf8")
        self.assertNotIn("GROQ_API_KEY",source)
        self.assertNotIn("GEMINI_API_KEY",source)
        self.assertNotIn("screen_news",source)
        self.assertNotIn("openai/gpt-oss",source)

if __name__ == "__main__":
    unittest.main()
