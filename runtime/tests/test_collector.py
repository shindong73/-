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
        self.assertEqual(set(collector.NEWS_FEEDS), {'KBS', 'MBC', 'JTBC'})
        self.assertNotIn('yna.co.kr', '\n'.join(collector.NEWS_FEEDS.values()))

    def test_breaking_filter_and_editorial_gate(self):
        self.assertTrue(collector.political_ok('[속보] 국회, 주요 법안 통과', block_negative=True))
        self.assertTrue(collector.political_ok('국회 의안 처리', block_negative=True))
        self.assertFalse(collector.political_ok('[속보] 야구 경기 취소', block_negative=True))
        self.assertFalse(collector.political_ok('[속보] 민주당 의원 구속 수사', block_negative=True))
        self.assertFalse(collector.political_ok('[속보] 이재명 대통령 사퇴 논란', block_negative=True))

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
        self.assertEqual(collector.rewrite_headline('[속보] 국회, 주요 법안 통과'), '국회가 주요 법안 통과')
        self.assertEqual(collector.rewrite_headline('[속보] 정부, 국정 현안 발표'), '정부가 국정 현안 발표')
        self.assertEqual(collector.rewrite_headline('[속보] "기밀 주장" 국회 발표'), '"기밀 주장" 국회 발표')
        self.assertEqual(collector.rewrite_headline('[속보] 원형 변경이 어려운 문장'), '원형 변경이 어려운 문장')

    def test_rss_parsing_verified_source(self):
        source='''<rss><channel><item><title>[속보] 국회, 주요 법안 통과 - KBS 뉴스</title><source>KBS 뉴스</source>
        <pubDate>Sun, 22 Nov 2026 00:59:00 +0000</pubDate><link>https://news.google.com/articles/a</link></item></channel></rss>'''
        with patch.object(collector, 'get_url', return_value=source.encode('utf8')):
            results=collector.fetch_rss('KBS', 'unused', T, SETTINGS)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['title'], '국회가 주요 법안 통과')
            self.assertEqual(results[0]['source'], 'KBS')
            self.assertNotIn('KBS', results[0]['title'])
            self.assertEqual(collector.fetch_rss('MBC', 'unused', T, SETTINGS), [])

    def test_usgs_minimum_4(self):
        sample={'features':[
            {'id':'abc','properties':{'mag':4.0,'time':int(T.timestamp()*1000),'place':'Near Busan','url':'https://earthquake.usgs.gov/earthquakes/eventpage/abc'}},
            {'id':'def','properties':{'mag':3.9,'time':int(T.timestamp()*1000),'place':'Near Seoul','url':'https://earthquake.usgs.gov/earthquakes/eventpage/def'}},
        ]}
        with patch.object(collector,'get_url',return_value=json.dumps(sample).encode()):
            results=collector.fetch_quakes(T, {'min_magnitude':4.0,'earthquake_region':{'minlatitude':31,'maxlatitude':44,'minlongitude':123,'maxlongitude':133},'earthquake_max_age_minutes':90})
        self.assertEqual(len(results),1)
        self.assertIn('4.0',results[0]['title'])

    def test_baseline_and_manual_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            config=root/'config.json'
            config.write_text('{}',encoding='utf8')
            seen=root/'data'/'seen.json'
            out=root/'site'/'data'/'alerts.json'
            alert={'id':'abc','kind':'politics','title':'국회가 주요 법안 통과','source':'KBS',
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
                another={**alert,'id':'abc2','title':'대통령이 국정 현안 검토'}
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
        xml = '''<rss><channel><item><title>국회 예산안 심사 일정 발표</title>
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
            event={'id':'lagged','kind':'politics','title':'국회 예산안 심사 일정 발표','source':'KBS',
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
                "title": "국회 주요 법안 처리", "source": "KBS",
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

    def test_direct_jtbc_source_validation(self):
        source = '''<rss><channel><item><title>국회 민주유공자법 의결</title>
        <pubDate>Sun, 22 Nov 2026 00:59:00 +0000</pubDate>
        <link>https://news.jtbc.co.kr/article/NB1234</link></item></channel></rss>'''
        with patch.object(collector, 'get_url', return_value=source.encode('utf8')):
            result=collector.fetch_rss('JTBC', collector.NEWS_FEEDS['JTBC'], T, SETTINGS)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['source'], 'JTBC')

if __name__ == '__main__':
    unittest.main()
