"""Regression tests: domestic civil-defense warning only, not missile coverage."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import collector

T = datetime(2026, 11, 22, 1, 0, tzinfo=timezone.utc)
CFG = {"headline_max_age_minutes": 180, "exclude_unfavorable_dem_news": True}


class CivilWarningTests(unittest.TestCase):
    def test_actual_issued_and_lifted_warning(self):
        self.assertEqual(
            collector.confirmed_warning_caption("[속보] 울릉도 경계경보 발령"),
            "울릉도 경계경보 발령")
        self.assertEqual(
            collector.confirmed_warning_caption("울릉군 경계경보 발령"),
            "울릉도 경계경보 발령")
        self.assertEqual(
            collector.confirmed_warning_caption("[속보] 울릉도 경계경보 해제"),
            "울릉도 경계경보 해제")
        self.assertEqual(
            collector.confirmed_warning_caption("울릉도 경계경보 발령 3분 만에 해제"),
            "울릉도 경계경보 해제")
        self.assertEqual(
            collector.confirmed_warning_caption("러시아 군용기 때문에 울릉도 경계경보 발령"),
            "울릉도 경계경보 발령")

    def test_missile_and_speculative_stories_never_become_warnings(self):
        for title in (
            "[속보] 북한 미사일 발사",
            "북한군, 탄도미사일 시험 발사",
            "북한 미사일 발사 가능성 경계",
            "울릉도 경계경보 발령 예정",
            "울릉도 경계경보 모의 훈련",
            "울릉도 경계경보 발령 검토",
            "울릉도 경계경보 발령 가능성",
            "전국 경계경보 발령 대비 훈련",
        ):
            with self.subTest(title=title):
                self.assertIsNone(collector.confirmed_warning_caption(title))
        self.assertFalse(collector.political_ok(
            "[속보] 국회 북한 탄도미사일 대응 논의", block_negative=False))
        self.assertFalse(collector.political_ok(
            "[속보] 정부 미사일 발사체 탐지", block_negative=False))

    def test_missile_cause_is_stripped_from_a_real_warning(self):
        self.assertEqual(
            collector.confirmed_warning_caption(
                "북한군 미사일 발사 이후 울릉도 경계경보 발령"),
            "울릉도 경계경보 발령")

    def test_publisher_verified_warning_rss(self):
        rss = """<rss><channel>
          <item><title>[속보] 울릉도 경계경보 발령 - KBS 뉴스</title>
            <pubDate>Sun, 22 Nov 2026 00:59:00 +0000</pubDate>
            <link>https://news.google.com/rss/articles/warning-1</link><source>KBS 뉴스</source></item>
          <item><title>[속보] 울릉군 경계경보 해제 - KBS 뉴스</title>
            <pubDate>Sun, 22 Nov 2026 00:59:00 +0000</pubDate>
            <link>https://news.google.com/rss/articles/warning-2</link><source>KBS 뉴스</source></item>
          <item><title>[속보] 북한 미사일 발사 - KBS 뉴스</title>
            <pubDate>Sun, 22 Nov 2026 00:59:00 +0000</pubDate>
            <link>https://news.google.com/rss/articles/missile</link><source>KBS 뉴스</source></item>
          <item><title>울릉도 경계경보 발령 훈련 - KBS 뉴스</title>
            <pubDate>Sun, 22 Nov 2026 00:59:00 +0000</pubDate>
            <link>https://news.google.com/rss/articles/drill</link><source>KBS 뉴스</source></item>
        </channel></rss>"""
        with patch.object(collector, "get_url", return_value=rss.encode("utf-8")):
            items = collector.fetch_rss("KBS", collector.WARNING_FEEDS[0][1], T, CFG)
        self.assertEqual(
            [(x["kind"], x["title"]) for x in items],
            [("warning", "울릉도 경계경보 발령"),
             ("warning", "울릉도 경계경보 해제")])

    def test_stale_warning_not_newly_selected(self):
        # An article from 40 minutes ago cannot look like a new active alert.
        rss = """<rss><channel><item>
          <title>[속보] 울릉도 경계경보 발령</title>
          <pubDate>Sun, 22 Nov 2026 00:20:00 GMT</pubDate>
          <link>https://news.google.com/rss/articles/old-alert</link>
          <source>KBS 뉴스</source>
        </item></channel></rss>"""
        with patch.object(collector, "get_url", return_value=rss.encode("utf-8")):
            found = collector.fetch_rss(
                "KBS", collector.WARNING_FEEDS[0][1], T,
                {**CFG, "warning_max_age_minutes": 15})
        self.assertEqual(found, [])

    def test_stale_active_warning_is_not_carried_over(self):
        import json
        import tempfile
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.json"
            config.write_text('{"warning_max_age_minutes":15}', encoding="utf8")
            seen = root / "seen.json"
            seen.write_text('{"initialized":true,"seen":{}}', encoding="utf8")
            out = root / "payload.json"
            old = {
                "id":"old-warning-1", "kind":"warning",
                "title":"울릉도 경계경보 발령",
                "source_title":"[속보] 울릉도 경계경보 발령",
                "source":"KBS",
                "published_at":collector.iso(T-timedelta(minutes=40)),
                "detected_at":collector.iso(T-timedelta(minutes=1))
            }
            out.write_text(json.dumps({"items":[old], "history":[]},
                                      ensure_ascii=False), encoding="utf8")
            with patch.object(collector,"CONFIG_PATH",config), \
                 patch.object(collector,"STORE_PATH",seen), \
                 patch.object(collector,"OUT_PATH",out), \
                 patch.object(collector,"now_utc",return_value=T), \
                 patch.object(collector,"fetch_rss",return_value=[]), \
                 patch.object(collector,"fetch_quakes",return_value=[]):
                result = collector.run("live")
            self.assertEqual(result["items"], [])

    def test_issuance_is_not_deduplicated_as_cancellation(self):
        self.assertFalse(collector.same_story(
            "울릉도 경계경보 발령", "울릉도 경계경보 해제"))


if __name__ == "__main__":
    unittest.main()
