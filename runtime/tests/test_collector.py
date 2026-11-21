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
        self.assertEqual(set(collector.NEWS_FEEDS), {'KBS', 'MBC'})
        self.assertNotIn('yna.co.kr', '\n'.join(collector.NEWS_FEEDS.values()))

    def test_breaking_filter_and_editorial_gate(self):
        self.assertTrue(collector.political_ok('[속보] 국회, 주요 법안 통과', block_negative=True))
        self.assertFalse(collector.political_ok('국회 의안 처리', block_negative=True))
        self.assertFalse(collector.political_ok('[속보] 야구 경기 취소', block_negative=True))
        self.assertFalse(collector.political_ok('[속보] 민주당 의원 구속 수사', block_negative=True))
        self.assertFalse(collector.political_ok('[속보] 이재명 대통령 사퇴 논란', block_negative=True))

    def test_rewrite_is_nonidentical(self):
        self.assertEqual(collector.rewrite_headline('[속보] 국회, 주요 법안 통과'), '국회가 주요 법안 통과')
        self.assertEqual(collector.rewrite_headline('[속보] 정부, 국정 현안 발표'), '정부가 국정 현안 발표')
        self.assertIsNone(collector.rewrite_headline('[속보] "기밀 주장" 국회 발표'))
        self.assertIsNone(collector.rewrite_headline('[속보] 원형 변경이 어려운 문장'))

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
                another={**alert,'id':'abc2'}
                with patch.object(collector,'fetch_rss',return_value=[alert,another]):
                    third=collector.run('live')
                self.assertIn('abc2',[x['id'] for x in third['items']])

if __name__ == '__main__':
    unittest.main()
