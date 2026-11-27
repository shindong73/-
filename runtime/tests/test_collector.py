import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import collector

T = datetime(2026, 11, 22, 1, 0, tzinfo=timezone.utc)
SETTINGS = {'exclude_unfavorable_dem_news': True, 'headline_max_age_minutes': 90}

class CollectorTests(unittest.TestCase):
    def test_only_broadcaster_feeds(self):
        self.assertEqual(set(collector.NEWS_FEEDS), {'KBS', 'MBC', 'JTBC', '연합뉴스'})
        self.assertIn('yna.co.kr', '\n'.join(collector.NEWS_FEEDS.values()))

    def test_breaking_filter_and_editorial_gate(self):
        self.assertTrue(collector.political_ok('[속보] 국회, 주요 법안 통과', block_negative=True))
        self.assertTrue(collector.political_ok('국회 의안 처리', block_negative=True))
        self.assertFalse(collector.political_ok('[속보] 야구 경기 취소', block_negative=True))
        self.assertFalse(collector.political_ok('[속보] 민주당 의원 구속 수사', block_negative=True))
        self.assertFalse(collector.political_ok('[속보] 이재명 대통령 사퇴 논란', block_negative=True))

    def test_party_commentary_cannot_masquerade_as_resignation_breaking(self):
        commentary = [
            '국힘 "수능마저 못 믿는 나라…최교진 사퇴로 끝날 일 아냐"',
            '[속보] 국힘 "수능마저 못 믿는 나라…최교진 사퇴로 끝날 일 아냐"',
            '국민의힘, 최교진 사퇴로 끝날 일 아니다',
            '국민의힘, 최교진 장관 사의 관련 논평',
            '민주당 "장관 사퇴만으론 책임 다 못 져"',
            '민주 "교육부 장관 사퇴 논란, 책임 물어야"',
            '조국혁신당 "최교진 사퇴만으로는 부족"',
            '민주당, 국민의힘 주장에 반박',
            '국민의힘 "장관 임명 철회해야"',
        ]
        for title in commentary:
            with self.subTest(title=title):
                self.assertTrue(collector.party_commentary(title))
                self.assertFalse(collector.confirmed_personnel_news(title))
                self.assertFalse(collector.political_ok(title, block_negative=True))
                self.assertFalse(collector.important_politics_news(title))
        factual = [
            '최교진 교육부 장관 사의 표명',
            '[긴급] 최교진 장관 사퇴 의사 밝혀',
            '대통령실, 신임 교육부 차관 임명 확정',
            '[속보] 국민의힘 당대표 사임 발표',
        ]
        for title in factual:
            with self.subTest(title=title):
                self.assertFalse(collector.party_commentary(title))
                self.assertTrue(collector.political_ok(title, block_negative=True))

    def test_broadcaster_rss_drops_party_reactions(self):
        rss = '''<rss><channel>
        <item><title>[속보] 국힘 "수능마저 못 믿는 나라…최교진 사퇴로 끝날 일 아냐"</title>
        <pubDate>Sun, 22 Nov 2026 00:59:00 GMT</pubDate>
        <link>https://news.google.com/rss/articles/party</link><source>KBS 뉴스</source></item>
        <item><title>[긴급] 최교진 교육부 장관 사의 표명</title>
        <pubDate>Sun, 22 Nov 2026 00:59:00 GMT</pubDate>
        <link>https://news.google.com/rss/articles/personnel</link><source>KBS 뉴스</source></item>
        </channel></rss>'''
        with patch.object(collector, "get_url", return_value=rss.encode()):
            found = collector.fetch_rss("KBS", collector.NEWS_FEEDS["KBS"], T, SETTINGS)
        self.assertEqual(len(found), 1)
        self.assertIn("최교진", found[0]["title"])

    def test_exclude_opposition_street_rally_and_response(self):
        blocked = [
            "국민의힘 대구 장외집회 개최 이재명 정부 압박",
            "민주당 국민의힘 대구 장외집회 비판",
            "국민의힘 대구 장외투쟁에 민주당 반박",
            "대구 장외집회 두고 민주당과 국민의힘 공방",
            "보수단체 이재명 퇴진 집회 개최",
        ]
        for title in blocked:
            with self.subTest(title=title):
                self.assertFalse(collector.political_ok(title, block_negative=True))
        allowed = [
            "이재명 대통령 울산 전통시장 방문",
            "국민의힘 국회 예산안 협상 참여",
            "대구시 국회에 교통 예산 증액 요청",
            "민주당 정부 정책 발표",
        ]
        for title in allowed:
            with self.subTest(title=title):
                self.assertTrue(collector.political_ok(title, block_negative=True))

    def test_november_23_cabinet_reshuffle_should_be_eligible(self):
        confirmed = [
            '[속보] 李대통령, 국정원장 후보자로 강금실 전 장관 지명',
            '[속보] 청 "국정원장 후보자에 강금실‥행안장관 한준호, 문체장관 강유정"',
            '이 대통령, 국정원장 후보자 강금실·외교장관 임웅순·통일장관 홍익표 지명',
            '[속보] 국정원장 강금실·외교 임웅순·행안 한준호·통일 홍익표·문체 강유정',
        ]
        for title in confirmed:
            with self.subTest(title=title):
                self.assertTrue(collector.domestic_politics_only(title))
                self.assertTrue(collector.political_ok(title, block_negative=True))
                self.assertTrue(collector.important_politics_news(title))
        self.assertTrue(collector.confirmed_personnel_news(confirmed[0]))
        self.assertTrue(collector.confirmed_personnel_news(confirmed[2]))
        rejected = [
            '국정원장 강금실 교체설 유력',
            '차기 국정원장 강금실 유력 전망',
            '미국 외교장관 경질 발표',
            '국힘 "국정원장 인선 졸속" 비판',
        ]
        for title in rejected:
            with self.subTest(title=title):
                self.assertFalse(collector.political_ok(title, block_negative=True))

    def test_foreign_world_headlines_are_excluded(self):
        foreign = [
            "FBI 트럼프 부정선거 주장 조사 착수",
            "미국 FBI 트럼프 대선 부정선거 의혹",
            "일본 총리 국회 해산 추진",
            "중국 정부, 대통령 선거 결과 발표",
            "러시아 대통령 우크라이나 관련 회담",
            "유럽 의회 정치 개혁안 가결",
            "영국 총리 의회 선거 일정 발표",
            "이스라엘 정부 가자지구 공격 승인",
            "북한 김정은 국정 운영 개편",
            "이재명 대통령 미국 외교 정상회담",
            "남아공 대통령 선거 결과 발표",
            "에티오피아 정부 총리 임명",
            "페루 정부 대통령 사임",
        ]
        for title in foreign:
            with self.subTest(title=title):
                self.assertFalse(collector.political_ok(title, block_negative=True))
        domestic = [
            "이재명 대통령 국무회의 개최",
            "국회 예산안 심사 본격화",
            "국민의힘, 국회 주요 법안 처리 방침",
            "민주당 대구 민생 정책 토론회 개최",
            "정부 수능 부정행위 신고 제도 개선",
        ]
        for title in domestic:
            with self.subTest(title=title):
                self.assertTrue(collector.political_ok(title, block_negative=True))

    def test_rewrite_is_nonidentical(self):
        self.assertEqual(collector.rewrite_headline('[속보] 국회, 주요 법안 통과'), '국회서 주요 법안 통과')
        self.assertEqual(collector.rewrite_headline('[속보] 정부, 국정 현안 발표'), '국정 현안…정부 발표')
        # If a factual, nonverbatim paraphrase is not safe, do not broadcast.
        self.assertIsNone(collector.rewrite_headline('[속보] "기밀 주장" 국회 발표'))
        self.assertIsNone(collector.rewrite_headline('[속보] 원형 변경이 어려운 문장'))
        self.assertEqual(
            collector.rewrite_headline("[긴급] 최교진, '수능 대혼란' 책임지고 사의…'준비 미흡 비판 통감'"),
            "최교진 사의 표명…수능 대혼란 책임"
        )
        self.assertEqual(
            collector.rewrite_headline('민주 "연내 조희대 탄핵 추진…한덕수 판결 내용은 사유에 미포함"'),
            "민주당, 조희대 탄핵 연내 추진…한덕수 판결 내용은 사유에서 제외"
        )
        self.assertEqual(
            collector.rewrite_headline('국민의힘 “코스피 급락 ‘블랙먼데이’ 우려…긴급 대응 조치 준비해야”'),
            "국민의힘, 코스피 급락 블랙먼데이 우려…긴급 대응 촉구"
        )
        self.assertEqual(
            collector.rewrite_headline("경제부총리 오늘 긴급 F4회의 소집…국내 증시 안정 대책 논의"),
            "경제부총리 긴급 F4회의 소집…국내 증시 안정 방안 논의"
        )
        self.assertIsNone(collector.rewrite_headline('최민희 "확인되지 않은 의혹"'))
        self.assertEqual(
            collector.rewrite_headline('[속보] 국회, 법안 부결'),
            "국회서 법안 부결"
        )


    def test_rss_parsing_verified_source(self):
        source='''<rss><channel><item><title>[속보] 국회, 주요 법안 통과 - KBS 뉴스</title><source>KBS 뉴스</source>
        <pubDate>Sun, 22 Nov 2026 00:59:00 +0000</pubDate><link>https://news.google.com/articles/a</link></item></channel></rss>'''
        with patch.object(collector, 'get_url', return_value=source.encode('utf8')):
            results=collector.fetch_rss('KBS', 'unused', T, SETTINGS)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['title'], '국회서 주요 법안 통과')
            self.assertEqual(results[0]['source'], 'KBS')
            self.assertNotIn('KBS', results[0]['title'])
            self.assertEqual(collector.fetch_rss('MBC', 'unused', T, SETTINGS), [])

    def test_usgs_is_disabled_and_never_requests_network(self):
        # Retired integration must never resurrect even if called directly.
        with patch.object(collector, "get_url", side_effect=AssertionError("USGS called")):
            result = collector.fetch_quakes(T, {})
        self.assertEqual(result, [])

    def test_baseline_and_manual_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            config=root/'config.json'
            config.write_text('{}',encoding='utf8')
            seen=root/'data'/'seen.json'
            out=root/'site'/'data'/'alerts.json'
            alert={'id':'abc','kind':'politics','title':'국회서 주요 법안 통과','source':'KBS',
                   'published_at':collector.iso(T),'link':'https://news.google.com/abc','is_test':False}
            with patch.object(collector,'CONFIG_PATH',config),patch.object(collector,'STORE_PATH',seen),patch.object(collector,'OUT_PATH',out),patch.object(collector,'now_utc',return_value=T),patch.object(collector,'fetch_rss',return_value=[alert]),patch.object(collector,'fetch_quakes',return_value=[]):
                first=collector.run('live')
                self.assertEqual(first['items'],[])
                second=collector.run('live')
                self.assertEqual(second['items'],[])
                self.assertEqual(second['generated_at'],first['generated_at'])
                test=collector.run('test_earthquake')
                self.assertEqual(len(test['items']),1)
                self.assertTrue(test['items'][0]['is_test'])
                self.assertIn('[테스트]', test['items'][0]['title'])
                another={**alert,'id':'abc2','title':'국회가 주요 예산안 가결'}
                with patch.object(collector,'fetch_rss',return_value=[alert,another]):
                    third=collector.run('live')
                self.assertIn('abc2',[x['id'] for x in third['items']])

    def test_same_story_across_outlets(self):
        self.assertTrue(collector.same_story('국회 민주유공자법 통과', '국회 민주유공자법 의결'))
        self.assertTrue(collector.same_story('이 대통령, 울산 전통시장 방문', '이 대통령 울산 전통시장 방문'))
        self.assertFalse(collector.same_story('이 대통령 울산 전통시장 방문', '이 대통령 울산 AI 데이터센터 방문'))

    def test_cross_outlet_realistic_headline_variants(self):
        self.assertTrue(collector.same_story(
            '이 대통령 수능 부정행위 신고포상금 건당 최소 1억 행위자 수만큼 가산',
            '이 대통령 수능 부정행위 포상금 최대 아닌 최소 1억 가담자 수만큼 증액'
        ))
        self.assertTrue(collector.same_story(
            '李 울산 SK AI데이터센터 방문 국가 경쟁 위해 속도전이 핵심',
            '이 대통령 울산 SK AI 데이터센터 방문 AI 고속도로가 AI 대전환 열 것'
        ))
        self.assertTrue(collector.same_story(
            '이 대통령 울산 전통시장서 장바구니 물가 점검 내년엔 좀 더 좋아질 것',
            '이 대통령 울산 전통시장 두 곳 방문 내년에는 조금 더 좋아질 것'
        ))
        self.assertFalse(collector.same_story(
            '민주당 조희대 대법원장 탄핵 추진',
            '민주당 조희대 대법원장 탄핵 철회'
        ))

    def test_direct_mbc_politics_feed_and_timezone(self):
        xml = '''<rss><channel><item><title>[속보] 국회, 예산안 가결</title>
        <pubDate>Sun, 22 Nov 2026 09:59:00 +0900</pubDate>
        <link>https://imnews.imbc.com/news/2026/politics/article/12345.html</link></item></channel></rss>'''
        with patch.object(collector,'get_url',return_value=xml.encode()):
            found=collector.fetch_rss('MBC', collector.MBC_DIRECT_POLITICS_RSS, T, SETTINGS)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['published_at'],'2026-11-22T00:59:00Z')

    def test_feed_lag_does_not_suppress_newly_detected_news(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cfg=root/'config.json'
            cfg.write_text('{"headline_max_age_minutes":90}',encoding='utf8')
            seen=root/'seen.json'
            seen.write_text('{"initialized":true,"seen":{}}',encoding='utf8')
            out=root/'feed.json'
            event={'id':'lagged','kind':'politics','title':'국회가 예산안 통과',
                   'source_title':'[속보] 국회, 예산안 통과','source':'KBS',
                   'published_at':collector.iso(T-collector.timedelta(minutes=40)),
                   'link':'https://news.google.com/example','is_test':False}
            with patch.object(collector,'CONFIG_PATH',cfg),patch.object(collector,'STORE_PATH',seen),patch.object(collector,'OUT_PATH',out),patch.object(collector,'now_utc',return_value=T),patch.object(collector,'fetch_rss',return_value=[event]),patch.object(collector,'fetch_quakes',return_value=[]):
                first=collector.run('live')
                self.assertEqual(first['items'][0]['published_at'],event['published_at'])
                self.assertEqual(first['items'][0]['detected_at'],collector.iso(T))
                with patch.object(collector,'now_utc',return_value=T+collector.timedelta(minutes=5)),patch.object(collector,'fetch_rss',return_value=[]):
                    next_check=collector.run('live')
                self.assertEqual(len(next_check['items']),1)

    def test_encrypted_delivery_history_excludes_test_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.json"
            config.write_text('{}', encoding='utf8')
            seen = root / "seen.json"
            seen.write_text('{"initialized":true,"seen":{}}', encoding='utf8')
            private = root / "private.json"
            news = {
                "id": "domestic-story-1", "kind": "politics",
                "title": "국회가 주요 법안 가결",
                "source_title":"[속보] 국회, 주요 법안 가결",
                "source": "KBS",
                "published_at": collector.iso(T), "link": "https://news.google.com/1",
                "is_test": False,
            }
            with patch.object(collector, "CONFIG_PATH", config), \
                 patch.object(collector, "STORE_PATH", seen), \
                 patch.object(collector, "OUT_PATH", private), \
                 patch.object(collector, "now_utc", return_value=T), \
                 patch.object(collector, "fetch_rss", return_value=[news]), \
                 patch.object(collector, "fetch_quakes", return_value=[]):
                first = collector.run("live")
                self.assertEqual(len(first["delivery_log"]), 1)
                self.assertEqual(first["delivery_log"][0]["title"], news["title"])
                self.assertEqual(first["delivery_log"][0]["display_seconds"], 30)
                second = collector.run("live")
                self.assertEqual(len(second["delivery_log"]), 1)
                test = collector.run("test_politics")
                self.assertEqual(len(test["delivery_log"]), 1)
                self.assertNotIn("테스트", test["delivery_log"][0]["title"])

    def test_health_heartbeat_persists_even_without_new_stories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root/'config.json'
            cfg.write_text('{}', encoding='utf8')
            seen = root/'seen.json'
            seen.write_text('{"initialized":true,"seen":{}}', encoding='utf8')
            out = root/'payload.json'
            with patch.object(collector,'CONFIG_PATH',cfg), \
                 patch.object(collector,'STORE_PATH',seen), \
                 patch.object(collector,'OUT_PATH',out), \
                 patch.object(collector,'fetch_rss',return_value=[]), \
                 patch.object(collector,'fetch_quakes',return_value=[]):
                with patch.object(collector,'now_utc',return_value=T):
                    a=collector.run('live')
                self.assertEqual(a['last_scan_at'],collector.iso(T))
                with patch.object(collector,'now_utc',return_value=T+collector.timedelta(minutes=10)):
                    b=collector.run('live')
                self.assertEqual(b['last_scan_at'],collector.iso(T))
                with patch.object(collector,'now_utc',return_value=T+collector.timedelta(minutes=16)):
                    c=collector.run('live')
                self.assertEqual(c['last_scan_at'],
                                 collector.iso(T+collector.timedelta(minutes=16)))
            self.assertEqual(json.loads(out.read_text())['last_scan_at'],c['last_scan_at'])

    def test_approved_rewritten_headline_remains_on_feed_and_in_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cfg=root/'config.json'
            cfg.write_text('{}',encoding='utf8')
            store=root/'seen.json'
            store.write_text('{"initialized":true,"seen":{}}',encoding='utf8')
            out=root/'private.json'
            selected={
                'id':'approved-1','kind':'politics','title':'새 후보자 다섯 명 발표',
                'source_title':'[속보] 청와대 국정원장 외교부 장관 인사 5명 지명',
                'source':'연합뉴스','published_at':collector.iso(T),
                'detected_at':collector.iso(T), 'is_breaking':True,
                'is_test':False
            }
            prior={'items':[selected],
                   'delivery_log':[{'id':'approved-1','kind':'politics',
                                   'title':'새 후보자 다섯 명 발표',
                                   'detected_at':collector.iso(T),
                                   'source':'연합뉴스'}],
                   'history':[],
                   'generated_at':collector.iso(T),
                   'last_scan_at':collector.iso(T)}
            out.write_text(json.dumps(prior,ensure_ascii=False),encoding='utf8')
            with patch.object(collector,'CONFIG_PATH',cfg), \
                 patch.object(collector,'STORE_PATH',store), \
                 patch.object(collector,'OUT_PATH',out), \
                 patch.object(collector,'now_utc',return_value=T+collector.timedelta(minutes=5)), \
                 patch.object(collector,'fetch_rss',return_value=[]), \
                 patch.object(collector,'fetch_quakes',return_value=[]):
                next_refresh=collector.run('live')
            self.assertEqual([x['id'] for x in next_refresh['items']],['approved-1'])
            self.assertEqual([x['id'] for x in next_refresh['delivery_log']],['approved-1'])

    def test_personnel_resignation_and_appointment_priority(self):
        confirmed = [
            "[긴급] 최교진, 수능 대혼란 책임지고 사의…준비 미흡 비판 통감",
            "교육부 장관 최교진 사의 표명",
            "교육부 차관 후임 발탁 결정",
            "국무총리 신임 장관 내정 발표",
            "대통령실 비서실장 교체",
            "최민희 국회 상임위원장 임명",
            "정청래 국회 인사 발표",
        ]
        for title in confirmed:
            with self.subTest(title=title):
                self.assertTrue(collector.political_ok(title, block_negative=True))
        self.assertTrue(collector.confirmed_personnel_news(confirmed[0]))
        self.assertTrue(collector.confirmed_personnel_news(confirmed[1]))
        self.assertTrue(collector.confirmed_personnel_news(confirmed[2]))
        unconfirmed = [
            "교육부 장관 사퇴 요구",
            "최교진 장관 사의 가능성 거론",
            "국무총리 새 장관 발탁설",
            "국회 장관 경질 촉구",
        ]
        for title in unconfirmed:
            with self.subTest(title=title):
                self.assertFalse(collector.political_ok(title, block_negative=True))

    def test_yonhap_google_news_publisher_validation(self):
        rss = '''<rss><channel><item>
        <title>[긴급] 최교진 교육부 장관 사의 표명 - 연합뉴스</title>
        <source url="https://www.yna.co.kr">연합뉴스</source>
        <pubDate>Sun, 22 Nov 2026 00:59:00 GMT</pubDate>
        <link>https://news.google.com/rss/articles/example</link>
        </item></channel></rss>'''
        with patch.object(collector, "get_url", return_value=rss.encode("utf8")):
            result = collector.fetch_rss("연합뉴스", collector.NEWS_FEEDS["연합뉴스"], T, SETTINGS)
        self.assertEqual(len(result), 1)
        self.assertIn("최교진", result[0]["title"])
        self.assertEqual(result[0]["source"], "연합뉴스")
        self.assertNotIn("- 연합뉴스", result[0]["title"])

    def test_only_substantive_politics_selected_for_rss(self):
        self.assertFalse(collector.important_politics_news("최민희 국회 행사 참석"))
        self.assertFalse(collector.important_politics_news("정청래 오늘 기자회견 참석"))
        self.assertFalse(collector.important_politics_news("이재명 대통령 전통시장 방문"))
        self.assertTrue(collector.important_politics_news("[긴급] 최교진 교육부 장관 사의 표명"))
        self.assertTrue(collector.important_politics_news("국회 주요 법안 가결"))
        rss = '''<rss><channel>
        <item><title>정청래 오늘 기자회견 참석</title>
        <pubDate>Sun, 22 Nov 2026 00:59:00 GMT</pubDate>
        <link>https://news.google.com/rss/articles/1</link><source>KBS 뉴스</source></item>
        <item><title>[긴급] 최교진 교육부 장관 사의 표명</title>
        <pubDate>Sun, 22 Nov 2026 00:59:00 GMT</pubDate>
        <link>https://news.google.com/rss/articles/2</link><source>KBS 뉴스</source></item>
        </channel></rss>'''
        with patch.object(collector, "get_url", return_value=rss.encode()):
            result=collector.fetch_rss("KBS",collector.NEWS_FEEDS["KBS"],T,SETTINGS)
        self.assertEqual(len(result),1)
        self.assertTrue(result[0]["is_breaking"])
        self.assertEqual(result[0]["title"],"최교진 교육부 장관 사퇴 의사 밝혀")

    def test_major_breaking_not_rate_limited_and_overflow_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cfg=root/'cfg.json'
            cfg.write_text('{"max_news_per_run":2}',encoding='utf8')
            store=root/'store.json'
            store.write_text('{"initialized":true,"seen":{}}',encoding='utf8')
            out=root/'private.json'
            base={'kind':'politics','source':'KBS','published_at':collector.iso(T),
                  'is_test':False,'is_breaking':True,'link':'https://news.google.com/1'}
            a={**base,'id':'a','title':'국회가 예산안 통과',
               'source_title':'[속보] 국회, 예산안 통과'}
            b={**base,'id':'b','title':'헌재가 주요 사건 선고',
               'source_title':'[속보] 헌재, 주요 사건 선고',
               'link':'https://news.google.com/2'}
            c={**base,'id':'c','title':'최교진 교육부 장관 사퇴 의사 밝혀',
               'source_title':'최교진 교육부 장관 사의 표명',
               'link':'https://news.google.com/3'}
            with patch.object(collector,'CONFIG_PATH',cfg),patch.object(collector,'STORE_PATH',store), \
                 patch.object(collector,'OUT_PATH',out),patch.object(collector,'fetch_quakes',return_value=[]), \
                 patch.object(collector,'same_story',return_value=False):
                with patch.object(collector,'now_utc',return_value=T), \
                     patch.object(collector,'fetch_rss',return_value=[a,b,c]):
                    first=collector.run('live')
                self.assertEqual(len(first['items']),2)
                persisted=json.loads(store.read_text(encoding='utf8'))['seen']
                self.assertEqual(len(persisted),2)
                self.assertTrue(any(x['id']=='c' for x in first['items']))
                with patch.object(collector,'now_utc',return_value=T+collector.timedelta(minutes=1)), \
                     patch.object(collector,'fetch_rss',return_value=[a,b,c]):
                    second=collector.run('live')
                self.assertEqual(set(x['id'] for x in second['items']), {'a','b','c'})
                self.assertEqual(len(json.loads(store.read_text(encoding='utf8'))['seen']),3)

    def test_direct_jtbc_source_validation(self):
        source = '''<rss><channel><item><title>국회 민주유공자법 의결</title>
        <pubDate>Sun, 22 Nov 2026 00:59:00 +0000</pubDate>
        <link>https://news.jtbc.co.kr/article/NB1234</link></item></channel></rss>'''
        with patch.object(collector, 'get_url', return_value=source.encode('utf8')):
            result=collector.fetch_rss('JTBC', collector.NEWS_FEEDS['JTBC'], T, SETTINGS)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['source'], 'JTBC')

    def test_naive_feed_timestamp_is_interpreted_as_utc(self):
        self.assertEqual(
            collector.iso(collector.parse_date("2026-11-23T01:03:00")),
            "2026-11-23T01:03:00Z"
        )
        self.assertEqual(
            collector.iso(collector.parse_date("Mon, 23 Nov 2026 01:03:00")),
            "2026-11-23T01:03:00Z"
        )

    def test_live_collection_never_calls_usgs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "config.json"
            cfg.write_text('{}', encoding="utf8")
            store = root / "seen.json"
            store.write_text('{"initialized":true,"seen":{}}', encoding="utf8")
            out = root / "feed.json"
            with patch.object(collector, "CONFIG_PATH", cfg), \
                 patch.object(collector, "STORE_PATH", store), \
                 patch.object(collector, "OUT_PATH", out), \
                 patch.object(collector, "now_utc", return_value=T), \
                 patch.object(collector, "fetch_rss", return_value=[]), \
                 patch.object(collector, "fetch_quakes", side_effect=AssertionError("USGS called")):
                data = collector.run("live")
            self.assertEqual(data["items"], [])
            self.assertEqual(data["last_check_errors"], [])

    def test_old_usgs_and_earthquake_entries_removed_from_active_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "config.json"
            cfg.write_text('{}', encoding="utf8")
            store = root / "seen.json"
            store.write_text('{"initialized":true,"seen":{}}', encoding="utf8")
            out = root / "feed.json"
            old_quake = {
                "id":"usgs-old123", "source":"USGS", "kind":"earthquake",
                "title":"한반도 인근 규모 4.4 지진 발생",
                "published_at":collector.iso(T),
                "detected_at":collector.iso(T),
                "is_test":False
            }
            old_korean = {
                "id":"old-news", "source":"KBS", "kind":"politics",
                "title":"국회가 예산안 가결",
                "source_title":"[속보] 국회, 예산안 가결",
                "is_breaking":True,
                "published_at":collector.iso(T),
                "detected_at":collector.iso(T),
                "is_test":False
            }
            out.write_text(json.dumps({"items":[old_quake,old_korean]},ensure_ascii=False),encoding="utf8")
            with patch.object(collector, "CONFIG_PATH", cfg), \
                 patch.object(collector, "STORE_PATH", store), \
                 patch.object(collector, "OUT_PATH", out), \
                 patch.object(collector, "now_utc", return_value=T+collector.timedelta(minutes=1)), \
                 patch.object(collector, "fetch_rss", return_value=[]), \
                 patch.object(collector, "fetch_quakes", side_effect=AssertionError("USGS called")):
                data = collector.run("live")
            self.assertNotIn("usgs-old123", [x["id"] for x in data["items"]])
            self.assertIn("old-news", [x["id"] for x in data["items"]])

    def test_rss_failure_and_recovery_are_persisted_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "config.json"
            cfg.write_text('{}', encoding='utf8')
            store = root / "seen.json"
            store.write_text('{"initialized":true,"seen":{}}', encoding='utf8')
            out = root / "payload.json"
            common = (
                patch.object(collector, "CONFIG_PATH", cfg),
                patch.object(collector, "STORE_PATH", store),
                patch.object(collector, "OUT_PATH", out),
                patch.object(collector, "fetch_quakes", return_value=[]),
            )
            from contextlib import ExitStack
            with ExitStack() as stack:
                for ctx in common:
                    stack.enter_context(ctx)
                with patch.object(collector, "now_utc", return_value=T), \
                     patch.object(collector, "fetch_rss", side_effect=RuntimeError("feed down")):
                    first = collector.run("live")
                self.assertIsNone(first["last_news_source_success_at"])
                self.assertTrue(first["last_check_errors"])
                self.assertEqual(json.loads(out.read_text(encoding="utf8"))["last_check_errors"],
                                 first["last_check_errors"])

                with patch.object(collector, "now_utc", return_value=T+collector.timedelta(minutes=1)), \
                     patch.object(collector, "fetch_rss", return_value=[]):
                    recovered = collector.run("live")
                self.assertEqual(recovered["last_news_source_success_at"],
                                 collector.iso(T+collector.timedelta(minutes=1)))
                self.assertEqual(json.loads(out.read_text(encoding="utf8"))["last_check_errors"], [])
                self.assertEqual(json.loads(out.read_text(encoding="utf8"))["last_news_source_success_at"],
                                 recovered["last_news_source_success_at"])

                with patch.object(collector, "now_utc", return_value=T+collector.timedelta(minutes=2)), \
                     patch.object(collector, "fetch_rss", side_effect=RuntimeError("feed down")):
                    failed_again = collector.run("live")
                self.assertEqual(failed_again["last_news_source_success_at"],
                                 recovered["last_news_source_success_at"])
                self.assertTrue(json.loads(out.read_text(encoding="utf8"))["last_check_errors"])

if __name__ == '__main__':
    unittest.main()
