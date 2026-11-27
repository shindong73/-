"""Policy regressions for OBS editorial exclusions and safe paraphrasing."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import collector

NOW = datetime(2026, 11, 24, 0, 40, tzinfo=timezone.utc)
CFG = {"headline_max_age_minutes": 180, "exclude_unfavorable_dem_news": True}


class EditorialPolicyTests(unittest.TestCase):
    def test_substantive_ordinary_headlines_are_allowed(self):
        # The ticker must not require every real Korean policy development
        # to be a cabinet shake-up or a high court judgment.
        samples = {
            "국회, 예산안 심사 착수": "국회가 예산안 심사 착수",
            "정부, 청년 주거지원 확대 발표": "정부가 청년 주거지원 확대 발표",
            "특검, 주요 사건 수사 착수": "특검이 주요 사건 수사 착수",
            "정부 주택정책 개편 시행": "정부가 주택정책 개편 시행",
            "국회, 법안 처리 합의…상임위 후속 논의": "국회가 법안 처리 합의",
            "보건복지부, 지원 대상 확대 발표": "보건복지부가 지원 대상 확대 발표",
            "국토교통부, 주택 공급계획 공개": "국토교통부가 주택 공급계획 공개",
        }
        for original, expected in samples.items():
            with self.subTest(title=original):
                self.assertTrue(collector.political_ok(original, block_negative=True))
                self.assertGreater(collector.headline_priority(original), 0)
                self.assertEqual(collector.rewrite_headline(original), expected)
                self.assertNotEqual(collector.rewrite_headline(original), original)

    def test_generic_government_still_requires_no_foreign_context(self):
        self.assertTrue(collector.political_ok(
            "정부, 청년 주거지원 확대 발표", block_negative=True))
        self.assertGreater(collector.headline_priority(
            "정부 주택정책 개편 시행"), 0)
        for foreign in (
            "에티오피아 정부 총리 임명",
            "페루 정부 대통령 사임",
            "남아공 정부 세제개편 발표",
            "미국 정부 주거지원 확대 발표",
        ):
            with self.subTest(foreign=foreign):
                self.assertFalse(collector.political_ok(
                    foreign, block_negative=True))

    def test_relaxed_rules_preserve_hard_safety_exclusions(self):
        excluded = (
            "[단독] 정부, 청년 주거지원 확대 발표",
            "선관위, 개표 관련 정책 발표",
            "정부, 부정선거 관련 대책 발표",
            "울산시, 경제자유구역청장 해임 발표",
            "국민의힘, 정부 정책 비판 논평",
            "정부, 지원 정책 검토 발표 예정",
            "이재명 대통령 전통시장 방문",
            "정부, 수사 착수설 확산",
            "북한 미사일 발사에 국회 긴급 대응",
        )
        for title in excluded:
            with self.subTest(title=title):
                self.assertEqual(collector.headline_priority(title), 0)

    def test_regular_verified_policy_story_survives_rss_gate(self):
        raw = (
            "<rss><channel><item><title>보건복지부, 지원 대상 확대 발표</title>"
            "<pubDate>Tue, 24 Nov 2026 00:39:00 GMT</pubDate>"
            "<link>https://news.google.com/rss/articles/policy</link>"
            "<source>KBS 뉴스</source></item></channel></rss>"
        )
        with patch.object(collector, "get_url", return_value=raw.encode("utf-8")):
            results = collector.fetch_rss("KBS", collector.NEWS_FEEDS["KBS"], NOW, CFG)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "보건복지부가 지원 대상 확대 발표")
        self.assertEqual(results[0]["priority"], 60)

    def test_quoted_official_document_titles_are_paraphrased(self):
        title = "국회, ‘청년지원법’ 본회의 통과"
        self.assertGreater(collector.headline_priority(title), 0)
        self.assertEqual(
            collector.rewrite_headline(title),
            "국회가 청년지원법 본회의 통과"
        )

        # An official announcement remains eligible even at a press briefing.
        self.assertGreater(collector.headline_priority(
            "정부, 기자회견 통해 청년 정책 발표"), 0)

        for excluded in (
            "조국혁신당, ‘청년 지원 확대’ 발표",
            "[단독] 국회, ‘청년지원법’ 본회의 통과",
            "선관위, ‘선거 결과’ 공식 발표"
        ):
            with self.subTest(excluded=excluded):
                self.assertEqual(collector.headline_priority(excluded), 0)

    def test_parliament_hearing_report_adoption_is_important_news(self):
        title = "법사위, 與 주도로 이용철 법무 후보자 청문보고서 채택"
        expected = ("이용철 법무부 장관 후보자 청문보고서, "
                    "국회 법사위에서 여당 주도로 채택")
        self.assertTrue(collector.political_ok(title, block_negative=True))
        self.assertTrue(collector.domestic_politics_only(title))
        self.assertEqual(collector.headline_priority(title), 90)
        self.assertEqual(collector.rewrite_headline(title), expected)
        self.assertNotEqual(expected, title)
        self.assertIn("법사위", collector.NEWS_FEEDS["MBC"])
        self.assertIn("청문보고서", collector.NEWS_FEEDS["MBC"])
        for variant, caption in (
            ("법사위, 이용철 법무장관 후보자 인사청문경과보고서 채택",
             "이용철 법무부 장관 후보자 청문보고서, 국회 법사위에서 채택"),
            ("[속보] 법사위, 여당 주도로 이용철 법무부 후보자 청문보고서 채택",
             expected),
        ):
            with self.subTest(variant=variant):
                self.assertGreater(collector.headline_priority(variant), 0)
                self.assertEqual(collector.rewrite_headline(variant), caption)

    def test_hearing_report_rss_mbc_source_and_exclusion_guards(self):
        title = "법사위, 與 주도로 이용철 법무 후보자 청문보고서 채택"
        raw = (
            "<rss><channel><item><title>" + title + "</title>"
            "<pubDate>Tue, 24 Nov 2026 00:39:00 GMT</pubDate>"
            "<link>https://news.google.com/rss/articles/hearing-report</link>"
            "<source>MBC 뉴스</source></item></channel></rss>"
        )
        with patch.object(collector, "get_url", return_value=raw.encode("utf-8")):
            selected = collector.fetch_rss("MBC", collector.NEWS_FEEDS["MBC"], NOW, CFG)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["priority"], 90)
        self.assertEqual(selected[0]["source"], "MBC")
        self.assertEqual(selected[0]["source_title"], title)
        self.assertNotEqual(selected[0]["title"], title)
        for blocked in (
            "[단독] " + title,
            title + " 예정",
            "법사위, 조국혁신당 주도로 이용철 법무 후보자 청문보고서 채택",
            "선관위, 이용철 법무 후보자 청문보고서 채택",
        ):
            with self.subTest(blocked=blocked):
                self.assertEqual(collector.headline_priority(blocked), 0)

    def test_confirmed_appeal_is_eligible_and_reworded(self):
        title = "특검, 추경호 '12·3 계엄 표결 방해' 1심 무죄에 항소"
        self.assertGreater(collector.headline_priority(title), 0)
        self.assertEqual(
            collector.rewrite_headline(title),
            "추경호 12·3 계엄 표결 방해 1심 무죄 판결…특검 항소"
        )
        rss = (
            "<rss><channel><item>"
            "<title>특검, 추경호 '12·3 계엄 표결 방해' 1심 무죄에 항소</title>"
            "<pubDate>Tue, 24 Nov 2026 00:39:00 GMT</pubDate>"
            "<link>https://news.google.com/rss/articles/appeal</link>"
            "<source>KBS 뉴스</source></item></channel></rss>"
        )
        with patch.object(collector, "get_url", return_value=rss.encode("utf-8")):
            got = collector.fetch_rss("KBS", collector.NEWS_FEEDS["KBS"], NOW, CFG)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["priority"], 80)
        self.assertEqual(got[0]["title"],
                         "추경호 12·3 계엄 표결 방해 1심 무죄 판결…특검 항소")
        self.assertNotEqual(got[0]["title"], got[0]["source_title"])

    def test_unconfirmed_appeal_does_not_become_concrete_event(self):
        for title in (
            "특검, 추경호 1심 무죄 판결 항소 검토",
            "특검, 추경호 1심 무죄 판결 항소 예정",
            "특검, 추경호 1심 무죄 판결 항소 촉구",
            "특검, 추경호 무죄 판결 비판",
        ):
            with self.subTest(title=title):
                self.assertEqual(collector.headline_priority(title), 0)

    def test_innovation_party_is_never_selected(self):
        samples = (
            "조국혁신당, 주요 법안 추진 발표",
            "[속보] 혁신당 원내대표 새 인선 발표",
            "국회 조국혁신당 의석 관련 처리 결정",
            "정부가 혁신당 공약 수용 발표",
        )
        for title in samples:
            with self.subTest(title=title):
                self.assertTrue(collector.excluded_ticker_topic(title))
                self.assertFalse(collector.political_ok(title, block_negative=True))
                self.assertEqual(collector.headline_priority(title), 0)

    def test_exclusive_badges_excluded_regardless_of_topic(self):
        exclusive = (
            "[단독] 국회, 예산안 최종 가결",
            "【단독】 이재명 대통령 신임 장관 지명",
            "(단독) 정부 주요 정책 발표",
            "［ 단독 ］ 울릉도 경계경보 발령",
            "[속보] [단독 보도] 국회 주요 법안 통과",
            "국회 주요 법안 가결 [단독]",
        )
        for title in exclusive:
            with self.subTest(title=title):
                self.assertTrue(collector.excluded_ticker_topic(title))
                self.assertFalse(collector.political_ok(title, block_negative=False))
                self.assertFalse(collector.important_politics_news(title))
                self.assertFalse(collector.confirmed_personnel_news(title))
        self.assertFalse(collector.excluded_ticker_topic(
            "[속보] 국회, 예산안 최종 가결"))
        self.assertFalse(collector.excluded_ticker_topic(
            "[속보] 단독 처리된 법안 공개"))

    def test_exclusive_tagged_warning_is_not_selected(self):
        warning = "[단독] 울릉도 경계경보 발령"
        self.assertIsNotNone(collector.confirmed_warning_caption(warning))
        # Classification alone is insufficient: exclusions apply before
        # category selection and must block the resulting warning item.
        original = (
            "<rss><channel><item><title>[단독] 울릉도 경계경보 발령</title>"
            "<pubDate>Tue, 24 Nov 2026 00:39:00 GMT</pubDate>"
            "<link>https://news.google.com/rss/articles/exclusive</link>"
            "<source>KBS 뉴스</source></item></channel></rss>"
        )
        with patch.object(collector, "get_url", return_value=original.encode("utf-8")):
            self.assertEqual(collector.fetch_rss(
                "KBS", collector.WARNING_FEEDS[0][1], NOW, CFG), [])

    def test_election_commission_topics_are_always_excluded(self):
        samples = (
            "특검 출범 후 첫 구속…나머지 선관위 직원 7명 기각",
            "[속보] 선거관리위원회 직원 구속",
            "[속보] 정부, 부정선거 의혹 수사",
            "[속보] 국회 투표 조작 문제 논의",
            "[속보] 사전투표 조작 논란",
        )
        for title in samples:
            with self.subTest(title=title):
                self.assertTrue(collector.excluded_ticker_topic(title))
                self.assertFalse(collector.political_ok(title, block_negative=True))
                self.assertFalse(collector.important_politics_news(title))
                self.assertFalse(collector.confirmed_personnel_news(title))

    def test_minor_local_personnel_not_national_breaking_news(self):
        samples = (
            "울산시, 이경식 울산경제자유구역청장 해임",
            "[속보] 부산시 부시장 경질",
            "서울시청 기획국장 임명 발표",
            "울산도시공사 사장 해임",
        )
        for title in samples:
            with self.subTest(title=title):
                self.assertTrue(collector.excluded_ticker_topic(title))
                self.assertFalse(collector.political_ok(title, block_negative=True))
                self.assertFalse(collector.confirmed_personnel_news(title))

    def test_national_events_and_local_nonpersonnel_not_blanket_blocked(self):
        for title in (
            "[속보] 국회, 예산안 가결",
            "[속보] 이재명 대통령, 신임 장관 지명",
            "[속보] 울산시, 재난 대응 계획 발표",
            "[속보] 국회, 지방선거법 개정안 통과",
        ):
            with self.subTest(title=title):
                self.assertFalse(collector.excluded_ticker_topic(title))
        self.assertTrue(collector.political_ok(
            "[속보] 국회, 예산안 가결", block_negative=True))
        self.assertTrue(collector.political_ok(
            "[속보] 이재명 대통령, 신임 장관 지명", block_negative=True))

    def test_publishers_titles_must_be_safely_reworded_or_dropped(self):
        self.assertEqual(collector.rewrite_headline(
            "[속보] 국회, 예산안 가결"), "국회가 예산안 가결")
        self.assertEqual(collector.rewrite_headline(
            "[속보] 교육부 장관 사의 표명"), "교육부 장관 사퇴 의사 밝혀")
        self.assertIsNone(collector.rewrite_headline(
            "[속보] 원형 변경이 어려운 문장"))
        self.assertIsNone(collector.rewrite_headline(
            "최민희 \"확인되지 않은 의혹\""))
        self.assertIsNone(collector.rewrite_headline(
            "[MBC 뉴스데스크 주요뉴스] 이 대통령 내각 개편 발표"))
        self.assertIsNone(collector.rewrite_headline(
            "[맞수토론] 이 대통령 개각 단행"))

    def test_verified_rss_drops_exclusions_before_editing(self):
        import xml.etree.ElementTree as ET
        items = [
            "[속보] 특검 출범 후 첫 구속…나머지 선관위 직원 7명 기각",
            "[속보] 울산시, 이경식 울산경제자유구역청장 해임",
            "[속보] 정부, 부정선거 의혹 조사 착수",
            "[속보] 국회, 주요 법안 가결",
        ]
        from xml.sax.saxutils import escape
        raw = "<rss><channel>" + "".join(
            f"<item><title>{escape(t)}</title>"
            "<pubDate>Tue, 24 Nov 2026 00:39:00 GMT</pubDate>"
            f"<link>https://news.google.com/rss/articles/{i}</link>"
            "<source>KBS 뉴스</source></item>"
            for i, t in enumerate(items)
        ) + "</channel></rss>"
        ET.fromstring(raw)
        with patch.object(collector, "get_url", return_value=raw.encode("utf-8")):
            selected = collector.fetch_rss(
                "KBS", collector.NEWS_FEEDS["KBS"], NOW, CFG)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["title"], "국회가 주요 법안 가결")
        self.assertEqual(selected[0]["source"], "KBS")

    def test_warning_and_missile_policy_unchanged(self):
        self.assertEqual(
            collector.confirmed_warning_caption("울릉도 경계경보 해제"),
            "울릉도 경계경보 해제")
        self.assertFalse(collector.political_ok(
            "[속보] 북한 미사일 발사", block_negative=True))


if __name__ == "__main__":
    unittest.main()
