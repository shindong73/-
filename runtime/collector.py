#!/usr/bin/env python3
"""Scheduled collector for the GitHub Pages OBS/PRISM breaking-news overlay.

Standard library only; use in GitHub Actions. Headlines are not independent
fact-checks. Review broadcasting permissions before public redistribution.
"""
from __future__ import annotations

import argparse
import hashlib
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed
from ai_filter import screen_news
import html
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
STORE_PATH = ROOT / "data" / "seen.json"
OUT_PATH = ROOT / "private" / "payload.json"
CONFIG_PATH = ROOT / "config.json"
UTC = timezone.utc

# RSS feeds are retrieved server-side: mobile devices do not directly contact them.
# KBS/MBC discovery via Google News; not official broadcaster RSS.
# JTBC primary feed is the user-provided breaking RSS.
# Google News searches are discovery only; original publisher is checked below.
# Extra focused personnel searches help keep time-sensitive Korean appointments
# from being buried in large general politics feeds.
NEWS_FEEDS = {
    "KBS": "https://news.google.com/rss/search?" + urlencode({
        "q": "site:news.kbs.co.kr (대통령 OR 국회 OR 민주당 OR 국민의힘 OR 특검 OR 정치 OR 계엄 OR 최교진 OR 최민희 OR 정청래 OR 장관 OR 발탁 OR 사의) when:6h",
        "hl": "ko", "gl": "KR", "ceid": "KR:ko"
    }),
    "MBC": "https://news.google.com/rss/search?" + urlencode({
        "q": "site:imnews.imbc.com (대통령 OR 국회 OR 민주당 OR 국민의힘 OR 특검 OR 정치 OR 계엄 OR 최교진 OR 최민희 OR 정청래 OR 장관 OR 발탁 OR 사의) when:6h",
        "hl": "ko", "gl": "KR", "ceid": "KR:ko"
    }),
    "JTBC": "https://news-ex.jtbc.co.kr/v1/get/rss/newsflesh",
    "연합뉴스": "https://news.google.com/rss/search?" + urlencode({
        "q": "site:yna.co.kr (대통령 OR 국회 OR 민주당 OR 국민의힘 OR 최교진 OR 최민희 OR 정청래 OR 장관 OR 차관 OR 발탁 OR 사퇴 OR 사의) when:6h",
        "hl": "ko", "gl": "KR", "ceid": "KR:ko"
    }),
}
JTBC_BACKUP = "https://fs.jtbc.co.kr/RSS/newsflash.xml"
MBC_DIRECT_POLITICS_RSS = "https://imnews.imbc.com/rss/news/news_01.xml"
JTBC_POLITICS_SEARCH = "https://news.google.com/rss/search?" + urlencode({
    "q": "site:news.jtbc.co.kr (대통령 OR 국회 OR 민주당 OR 국민의힘 OR 특검 OR 정치 OR 계엄 OR 최교진 OR 최민희 OR 정청래 OR 장관 OR 발탁 OR 사퇴) when:6h",
    "hl": "ko", "gl": "KR", "ceid": "KR:ko"
})
PERSONNEL_TERMS = "(사의 OR 사퇴 OR 사임 OR 사표 OR 발탁 OR 지명 OR 임명 OR 내정 OR 경질 OR 해임 OR 교체 OR 인선 OR 후보자)"
FOCUSED_FEEDS = [
    (source, "https://news.google.com/rss/search?" + urlencode({
        "q": f"site:{domain} (교육부 OR 최교진 OR 장관 OR 차관 OR 국무총리 OR 대통령실 OR 국정원장 OR 국가정보원 OR 외교부 OR 통일부 OR 행안부 OR 문체부 OR 개각) {PERSONNEL_TERMS} when:6h",
        "hl": "ko", "gl": "KR", "ceid": "KR:ko"
    }))
    for source, domain in (
        ("KBS", "news.kbs.co.kr"),
        ("MBC", "imnews.imbc.com"),
        ("JTBC", "news.jtbc.co.kr"),
        ("연합뉴스", "yna.co.kr"),
    )
]

# Domestic civil-defense warning discovery. These queries never promote a
# missile launch/military activity story unless a Korean area's 경계경보 was
# actually issued, lifted, or corrected in the verified publisher headline.
WARNING_FEEDS = [
    (source, "https://news.google.com/rss/search?" + urlencode({
        "q": f'site:{domain} ("경계경보" OR "경계 경보") when:6h',
        "hl": "ko", "gl": "KR", "ceid": "KR:ko"
    }))
    for source, domain in (
        ("KBS", "news.kbs.co.kr"),
        ("MBC", "imnews.imbc.com"),
        ("JTBC", "news.jtbc.co.kr"),
        ("연합뉴스", "yna.co.kr"),
    )
]

USGS_QUERY = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Select verified recent politics articles with or without a breaking badge.
BREAKING_RE = re.compile(r"(?:\[\s*(?:(?:긴급\s*)?속보|긴급)\s*\]|\(\s*속보\s*\)|【\s*속보\s*】|^\s*(?:속보|긴급)\s*[:：])", re.I)
POLITICAL_RE = re.compile(
    r"대통령|대통령실|청와대|국회|국정|정치|여당|야당|민주당|국민의힘|조국혁신당|"
    r"국무회의|정부|총리|장관|정당|선거|대선|총선|지방선거|의원|특검|탄핵|"
    r"검찰|헌법재판소|헌재|이재명|윤석열|정청래|김민석|조희대|계엄|내란|"
    r"민주유공자|사법개혁|정책발표|국정과제|공직|최교진|최민희|"
    r"교육부|교육장관|교육부장관|장관|차관|총리|부총리|"
    r"사의|사표|사퇴|사임|임명|발탁|내정|지명|경질|해임|인사|인선|개각|국정원장|국가정보원|외교부|통일부|행안부|문체부"
)
# Conservative editorial exclusion: title-only rules have false positives and false negatives.
# The overlay must not be described as neutral or comprehensive news coverage.
DEM_ACTORS = re.compile(r"더불어민주당|민주당|이재명|정청래|김민석|대통령실|현\s*정부|집권여당")
NEGATIVE_TERMS = re.compile(
    r"압수수색|소환|구속|체포|기소|유죄|징역|실형|비리|부패|뇌물|"
    r"사퇴|사임|징계|제명|불법|위법|벌금|당내\s*논란|공천\s*의혹|지지율\s*하락"
)
# Headline-only editorial selection is fallible; negative terms for unrelated
# public figures do not necessarily indicate criticism of the governing party.


# Exclude opposition-led anti-government street rallies and response stories
# about those same rallies. This is an editorial choice, not a neutral news feed.
RALLY_EVENT_RE = re.compile(
    r"장외\s*(?:집회|투쟁)|정권\s*규탄|(?:대통령|정권|정부|이재명)\s*(?:퇴진|규탄)|"
    r"반정부\s*(?:집회|시위)|퇴진\s*(?:집회|시위)"
)
RALLY_CONTEXT_RE = re.compile(
    r"국민의힘|국힘|보수\s*(?:단체|진영)|야당|대구|이재명|李\s*대통령"
)


def excluded_anti_government_rally(title: str) -> bool:
    return bool(RALLY_EVENT_RE.search(title) and RALLY_CONTEXT_RE.search(title))


# Deliberate editorial scope: this ticker covers South Korean domestic politics
# only. A Korean broadcaster covering foreign/world news does not make it domestic.
# First reject explicit foreign names and international events, then require an
# identifiable South Korean actor, institution or domestic-policy context.
FOREIGN_NEWS_RE = re.compile(
    r"\bFBI\b|\bCIA\b|\bEU\b|\bNATO\b|\bUN\b|\bG7\b|\bG20\b|"
    r"트럼프|바이든|푸틴|시진핑|젤렌스키|마크롱|다카이치|"
    r"미국|미\s*연방|美\s*(?:대선|정부|대통령|공화|민주|의회|연방|FBI|법원|증시)|"
    r"중국|中\s*(?:정부|당국|공산당|주석)|일본|日\s*(?:총리|정부|여당|야당)|"
    r"러시아|우크라이나|대만|홍콩|북한|평양|김정은|"
    r"영국|프랑스|독일|이탈리아|스페인|유럽|캐나다|호주|"
    r"인도네시아|베트남|태국|필리핀|싱가포르|인도|파키스탄|"
    r"이스라엘|팔레스타인|가자지구|이란|이라크|시리아|중동|"
    r"멕시코|브라질|아르헨티나|아프리카|남미|"
    r"국제\s*(?:뉴스|정세|사회|회의|기구|분쟁)|해외|외신|"
    r"정상회담|국제사회|유엔|연합국|중동전쟁|미군",
    re.I,
)
DOMESTIC_CONTEXT_RE = re.compile(
    r"대한민국|한국|국내|우리나라|이재명|이\s*대통령|李\s*대통령|尹\s*대통령|윤석열|최교진|"
    r"민주당|국민의힘|국힘|조국혁신당|정청래|최민희|김민석|조희대|추미애|교육부|"
    r"교육장관|교육부장관|국무위원|정부서울청사|정부세종청사|"
    r"국회|대통령실|청와대|국무회의|국무총리|국정|"
    r"헌법재판소|헌재|대법원|검찰|특검|지방선거|수능|교육부|"
    r"서울|경기|인천|부산|대구|광주|대전|울산|세종|충북|충남|"
    r"경북|경남|전북|전남|강원|제주|여의도|용산|"
    r"국회의원|행정안전부|기획재정부|금융위원회|민생|법무부|"
    r"국정원장|국가정보원|국정원|개각|인선|외교부|외교장관|통일부|통일장관|행안부|행안장관|문체부|문체장관|문화체육관광부|강금실|임웅순|홍익표|한준호|강유정",
    re.I,
)


def domestic_politics_only(title: str) -> bool:
    return bool(DOMESTIC_CONTEXT_RE.search(title) and
                not FOREIGN_NEWS_RE.search(title))


# Priority for substantive, confirmed Korean government appointments/exits.
# Mere demands, speculation or "should resign" stories are not confirmations.
GOVERNMENT_PERSONNEL_ACTOR_RE = re.compile(
    r"최교진|교육부|국무총리|부총리|국무위원|대통령실|장관|차관|"
    r"비서실장|수석비서관|청장|장관급|차관급|국정원장|국가정보원장|개각|외교부|통일부|행안부|문체부"
)
GOVERNMENT_PERSONNEL_ACTION_RE = re.compile(
    r"사의|사표|사직서|사퇴|사임|경질|해임|교체|발탁|내정|지명|임명"
)
UNCONFIRMED_APPOINTMENT_RE = re.compile(
    r"촉구|요구|압박|가능성|거론|검토|전망|발탁설|사퇴설|임명설|"
    r"인사설|교체설|지명설|내정설|하마평|유력|관측|하라|해야|할까|하나|추측|루머|확인\s*어렵|철회\s*요구"
)


# Criticism about a resignation is not an official personnel announcement.
# Exclude reactive statements from every political party consistently.
PARTY_NAME_PATTERN = r"(?:국민의힘|국힘|더불어민주당|민주당|민주|조국혁신당|혁신당)"
PARTY_QUOTED_OPINION_RE = re.compile(
    PARTY_NAME_PATTERN + r"\s*(?:대변인|대표|원내대표)?\s*(?:[:：,，]\s*)?[“\"‘'「『]"
)
PARTY_REACTION_RE = re.compile(
    PARTY_NAME_PATTERN + r".{0,55}?"
    r"(?:논평|반박|비판|비난|규탄|공세|책임론|공방|"
    r"못\s*믿|끝날\s*일\s*아냐|끝날\s*일\s*아니|"
    r"끝날\s*문제\s*아니|사퇴로\s*끝날|사퇴만으론|"
    r"사퇴에\s*그쳐선|책임\s*물어야)"
)


def party_commentary(title: str) -> bool:
    clean = BREAKING_RE.sub("", title, count=1).strip()
    return bool(PARTY_QUOTED_OPINION_RE.search(clean)
                or PARTY_REACTION_RE.search(clean))


def confirmed_personnel_news(title: str) -> bool:
    return bool(domestic_politics_only(title)
                and not party_commentary(title)
                and GOVERNMENT_PERSONNEL_ACTOR_RE.search(title)
                and GOVERNMENT_PERSONNEL_ACTION_RE.search(title)
                and not UNCONFIRMED_APPOINTMENT_RE.search(title))



def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        date = parsedate_to_datetime(s)
    except (ValueError, TypeError, IndexError):
        try:
            date = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    # Source feeds occasionally omit their timezone; treat such dates as UTC
    # instead of inheriting the runner's local timezone.
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    return date.astimezone(UTC)


def get_url(url: str, *, attempts: int = 2, timeout: int = 12) -> bytes:
    last_error = None
    for n in range(attempts):
        try:
            req = Request(url, headers={
                "User-Agent": "OBS-Korean-Breaking-Alerts/1.0 (+GitHub Pages; personal news monitor)",
                "Accept": "application/xml,text/xml,application/rss+xml,application/json,*/*",
            })
            with urlopen(req, timeout=timeout) as response:
                return response.read(4_000_000)
        except Exception as exc:
            last_error = exc
            if n < attempts - 1:
                time.sleep(2)
    raise RuntimeError(f"Failed {url}: {last_error}")


def read_json(path: Path, default: dict) -> dict:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_title(title: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", title or ""))
    text = re.sub(r"\s*[-|]\s*(?:KBS\s*뉴스|KBS뉴스|MBC\s*뉴스|MBC뉴스|MBC|JTBC\s*뉴스|JTBC|연합뉴스)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


MAJOR_DECISION_RE = re.compile(
    r"(?:국회|국무회의|헌법재판소|헌재|대법원|대통령실|선관위|정부)"
    r".{0,45}?(?:가결|부결|의결|법안\s*통과|예산안\s*통과|최종\s*확정|선고|파면|기각|발효|공포)"
)


# This is intentionally much narrower than domestic military coverage.
# Only a confirmed area-level 경계경보 change is an eligible alert.
WARNING_LOCATION_RE = re.compile(
    r"울릉도|울릉군|독도|백령도|연평도|연천군|파주시|철원군|고성군|강화군|"
    r"서울|부산|인천|대구|광주|대전|울산|세종|경기도|강원도|충청북도|충청남도|"
    r"전라북도|전라남도|경상북도|경상남도|제주도|경기|강원|충북|충남|전북|"
    r"전남|경북|경남|제주|(?:[가-힣]{2,8})(?:시|군)"
)
WARNING_UNCONFIRMED_RE = re.compile(
    r"훈련|모의|가상|예행|테스트|예고|예정|가능성|검토|대비|시뮬레이션|"
    r"오보|오발령|잘못\s*발령|발령\s*요청|발령\s*촉구|발령\s*시|"
    r"발령\s*때|발령\s*한다면|발령\s*방안"
)


def confirmed_warning_caption(title: str) -> str | None:
    """Only a reported domestic 경계경보 state change, never a missile headline.

    Strip any military explanation and retain just the region and alert state.
    This is an editorial news overlay, not a replacement for public alerts.
    """
    clean = clean_title(BREAKING_RE.sub("", title, count=1)).replace("경계 경보", "경계경보")
    if "경계경보" not in clean or WARNING_UNCONFIRMED_RE.search(clean):
        return None
    if not re.search(r"경계경보.{0,55}(?:발령|해제|정정)|(?:발령|해제|정정).{0,55}경계경보", clean):
        return None
    # Require a concrete Korean locality rather than a generic military event.
    locations = [match for match in WARNING_LOCATION_RE.finditer(clean)
                 if not match.group().startswith(("북한", "러시아"))]
    if not locations:
        return None
    alert_pos = clean.find("경계경보")
    # Prefer the locality closest to the actual warning rather than a foreign
    # military actor mentioned in a preceding explanatory clause.
    area = min(locations, key=lambda m: abs(m.start() - alert_pos)).group()
    if area in ("울릉도", "울릉군"):
        area = "울릉도"
    # A combined "issued and lifted" story reports the most recent state.
    state = "해제" if "해제" in clean else ("정정" if "정정" in clean else "발령")
    return f"{area} 경계경보 {state}"


def important_politics_news(title: str) -> bool:
    # Routine visits, remarks and party reactions are not a breaking headline.
    if party_commentary(title):
        return False
    return bool(confirmed_personnel_news(title)
                or BREAKING_RE.search(title)
                or MAJOR_DECISION_RE.search(title))


def political_ok(title: str, *, block_negative: bool) -> bool:
    # A missile report is not a domestic civil-defense warning. The separate
    # verified warning branch is the only way to show an issued 경계경보.
    if re.search(r"미사일|탄도탄|탄도미사일|발사체|ICBM|SLBM|북한|北\\s*(?:미사일|발사)", title, re.I):
        return False
    if not POLITICAL_RE.search(title) or not domestic_politics_only(title):
        return False
    if len(title) < 8 or re.search(r"\[광고\]|\[연예\]|오늘의\s*운세|야구\s*경기", title):
        return False
    if excluded_anti_government_rally(title) or party_commentary(title):
        return False
    # Don't imply that a resignation demand or an appointment rumor is final.
    if (GOVERNMENT_PERSONNEL_ACTOR_RE.search(title)
            and UNCONFIRMED_APPOINTMENT_RE.search(title)):
        return False
    if confirmed_personnel_news(title):
        return True
    if block_negative and DEM_ACTORS.search(title) and NEGATIVE_TERMS.search(title):
        return False
    return True


def rewrite_headline(original: str) -> str | None:
    """Create a concise, attributed broadcaster-style headline from verified RSS facts.

    Prefer meaningful but safe restructuring. This is deterministic and cannot
    guarantee that every headline is paraphrasable or free of copyright issues.
    Never turn a prediction, quote, allegation, demand or intention into a fact.
    """
    title = BREAKING_RE.sub("", original, count=1).strip(" \t:：-·")
    title = re.sub(r"\s+", " ", title).strip()
    if not title or len(title) < 8 or len(title) > 130:
        return None

    # An explicit responsibility-taking resignation can be summarized without
    # repeating the journalist's entire quote or adding speculative details.
    resignation = re.match(
        r"^(?P<person>[가-힣·]{2,12})\s*[,，]\s*"
        r"[‘'\"“]?(?P<reason>[^’‘'\"”“…‥]{3,40})[’'\"”]?"
        r"\s*책임지고\s*사의(?:\s*표명)?(?:\s*[.…‥].*)?$",
        title
    )
    if resignation:
        person, reason = resignation.group("person", "reason")
        return f"{person} 사의 표명…{reason.strip()} 책임"[:100]

    # Keep a political party as the *actor* of a quoted plan or demand.
    # Quote text is never reproduced inside quotation marks after paraphrase.
    attributed = re.fullmatch(
        r"(?P<speaker>민주|민주당|국힘|국민의힘)\s*[“\"]"
        r"(?P<statement>.+)[”\"]",
        title
    )
    if attributed:
        speaker = {"민주": "민주당", "국힘": "국민의힘"}.get(
            attributed.group("speaker"), attributed.group("speaker")
        )
        statement = attributed.group("statement").strip()
        # A documented plan remains a plan: do not promote it to a decision.
        planned = re.match(
            r"연내\s+(?P<subject>[가-힣·\s]{2,32}?)\s+탄핵\s+추진"
            r"\s*[.…‥]+\s*(?P<qualification>.+)$",
            statement
        )
        if planned:
            subject = planned.group("subject").strip()
            qualification = planned.group("qualification").strip()
            qualification = qualification.replace("사유에 미포함", "사유에서 제외")
            qualification = qualification.replace("사유에 포함 안 돼", "사유에서 제외")
            return f"{speaker}, {subject} 탄핵 연내 추진…{qualification}"[:100]
        market = re.match(
            r"(?P<concern>.+?우려)\s*[.…‥]+\s*(?P<response>.+?)"
            r"(?:준비해야|마련해야)\s*$",
            statement
        )
        if market:
            concern = re.sub(r"[‘’'\"“”]", "", market.group("concern")).strip()
            response = market.group("response").strip()
            response = re.sub(r"\s*(?:조치|대책)\s*$", "", response).strip()
            if concern and response:
                return f"{speaker}, {concern}…{response}{' 촉구' if response.endswith('대응') else ' 대응 촉구'}"[:100]
        # Do not substitute words inside a contested or otherwise complex quote.
        return title

    # A narrowly-scoped factual rewording, avoiding changes to who did what.
    paraphrases = (
        (r"\b사의를 표명\b", "사퇴 의사 밝혀"),
        (r"\b사의 표명\b", "사퇴 의사 밝혀"),
        (r"\b오늘\s+", ""),
        (r"\b국내 증시 안정 대책\b", "국내 증시 안정 방안"),
        (r"\b사유에 미포함\b", "사유에서 제외"),
    )
    for pattern, replacement in paraphrases:
        title = re.sub(pattern, replacement, title)

    # Factual subject-first broadcast wording when an explicit actor and a
    # complete factual action are present; not for direct quotations.
    if not re.search(r'[“”"「」『』‘’]', title):
        match = re.fullmatch(r"([가-힣A-Za-z0-9·\s]{2,24}?),\s+(.{4,90})", title)
        if match:
            actor, action = match.groups()
            if re.search(r"(발표|선포|의결|가결|통과|발의|요청|제출|합의|공개|"
                         r"확정|승인|지시|거부|부결|수용|제안|추진|개최|중단|결정|"
                         r"검토|촉구|임명)(?:했다|해|함|키로)?$", action):
                final = actor[-1]
                particle = '이' if '가' <= final <= '힣' and ((ord(final)-0xAC00) % 28) else '가'
                changed = f"{actor}{particle} {action}"
                if len(changed) <= 100:
                    return changed

    # If a safe, meaningful rewrite is unavailable, retain the factual wording
    # rather than manufacture a new claim. No copyright guarantee is implied.
    return title[:110]


def normalized_story(title: str) -> str:
    text = clean_title(BREAKING_RE.sub("", title, count=1)).lower()
    # Normalize spelling variants of the same event; do not remove decisive
    # words such as '철회', '부결', '확정', or '추진'.
    text = text.replace("ai데이터센터", "ai 데이터센터")
    text = text.replace("전통시장서", "전통시장")
    text = text.replace("신고포상금", "포상금")
    text = text.replace("내년에는", "내년").replace("내년엔", "내년")
    text = text.replace("행위자", "가담자")
    text = re.sub(r"[^가-힣a-z0-9]+", " ", text).strip()
    for old, new in (("이 대통령", "이재명 대통령"), ("국회서", "국회"),
                     ("통과", "의결"), ("대법원장", "조희대"),
                     ("대통령이", "대통령"), ("대통령은", "대통령")):
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text)


def same_story(a: str, b: str) -> bool:
    """Conservative same-event test across different broadcaster headlines."""
    # Contradictory event outcomes must not be silently treated as duplicates.
    contradictory = (("발령", "해제"), ("추진", "철회"), ("추진", "중단"), ("가결", "부결"),
                     ("통과", "부결"), ("승인", "거부"), ("확정", "검토"),
                     ("찬성", "반대"), ("기소", "무혐의"))
    for left, right in contradictory:
        if (left in a and right in b) or (left in b and right in a):
            return False
    x, y = normalized_story(a), normalized_story(b)
    if not x or not y:
        return False
    if x == y:
        return True
    sim = SequenceMatcher(None, x, y, autojunk=False).ratio()
    stop = {"대통령", "이재명", "정부", "국회", "민주당", "국민의힘", "오늘",
            "관련", "정치", "여야", "발표", "방문", "기자", "속보",
            "국회가", "국회는", "장관", "위원", "후보", "더", "것"}
    xx = {word for word in x.split() if word not in stop}
    yy = {word for word in y.split() if word not in stop}
    common = xx & yy
    union = xx | yy
    jaccard = len(common) / len(union) if union else 0
    # Near-identical wording, or enough shared distinctive event details.
    return (sim >= .90 or
            (len(common) >= 3 and jaccard >= .24 and sim >= .57) or
            (len(common) >= 2 and jaccard >= .47 and sim >= .72))


def stable_id(kind: str, link: str, title: str) -> str:
    return kind + "-" + hashlib.sha256((link or title).encode("utf-8")).hexdigest()[:24]


def fetch_rss(source: str, url: str, current: datetime, settings: dict) -> list[dict]:
    optional_direct = url in {JTBC_BACKUP, NEWS_FEEDS["JTBC"], MBC_DIRECT_POLITICS_RSS}
    root = ET.fromstring(get_url(
        url, attempts=1 if optional_direct else 2,
        timeout=6 if optional_direct else 12
    ))
    items = []
    counters = {"raw": 0, "politics": 0, "recent": 0, "source": 0}
    candidates = root.findall(".//item") or root.findall(".//{*}entry")
    ages_minutes = []
    for item in candidates:
        counters["raw"] += 1
        title = clean_title(item.findtext("title") or item.findtext("{*}title") or "")
        warning_title = confirmed_warning_caption(title)
        # Don't let articles *about* warnings or missile launches slip into
        # the ordinary politics ticker as a workaround.
        if not warning_title and (
                "경계경보" in title.replace(" ", "")
                or not political_ok(title, block_negative=bool(settings["exclude_unfavorable_dem_news"]))
                or not important_politics_news(title)):
            continue
        counters["politics"] += 1
        published = parse_date(item.findtext("pubDate") or item.findtext("published") or
                               item.findtext("{*}published") or item.findtext("{*}updated"))
        if published:
            ages_minutes.append(round((current - published).total_seconds()/60))
        if not published or not (current - timedelta(minutes=settings["headline_max_age_minutes"]) <= published <= current + timedelta(minutes=5)):
            continue
        counters["recent"] += 1
        link = (item.findtext("link") or "").strip()
        if not link:
            node = item.find("{*}link")
            if node is None:
                node = item.find("link")
            if node is not None:
                link = (node.get("href") or node.text or "").strip()
        if not link.startswith("https://"):
            continue
        if "news.google.com" in url or source == "KBS" or (source == "MBC" and "imnews.imbc.com" not in url):
            # Google News is discovery, so the original publisher must match.
            source_name = (item.findtext("source") or "").strip().upper()
            expected_names = ("연합뉴스", "YONHAP") if source == "연합뉴스" else (source,)
            if not any(name in source_name for name in expected_names):
                continue
        else:
            # The JTBC first-party RSS must point to an actual JTBC article.
            host = (urlparse(link).hostname or "").lower()
            expected = "imbc.com" if source == "MBC" else "jtbc.co.kr"
            if not (host == expected or host.endswith("." + expected)):
                continue
        counters["source"] += 1
        rewritten = warning_title or rewrite_headline(title)
        if not rewritten:
            continue
        items.append({
            "id": stable_id(source, link, title),
            "kind": "warning" if warning_title else "politics",
            "title": rewritten,
            "source_title": title,
            "source": source,
            "published_at": iso(published),
            "link": link,
            "is_test": False,
            "is_breaking": bool(BREAKING_RE.search(title)),
        })
    # Counts only. Never log article headlines or broadcast labels publicly.
    youngest = min(ages_minutes) if ages_minutes else "n/a"
    print(f"RSS {source}: seen={counters['raw']} political={counters['politics']} "
          f"recent={counters['recent']} verified={counters['source']} eligible={len(items)} "
          f"youngest_age_min={youngest}")
    return items


def fetch_quakes(current: datetime, settings: dict) -> list[dict]:
    # Korea + nearby seas. The USGS regional rectangle can be edited in config.json.
    r = settings["earthquake_region"]
    args = {
        "format": "geojson",
        "starttime": (current - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": current.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": settings["min_magnitude"],
        "minlatitude": r["minlatitude"], "maxlatitude": r["maxlatitude"],
        "minlongitude": r["minlongitude"], "maxlongitude": r["maxlongitude"],
        "orderby": "time", "limit": 80,
    }
    feed = json.loads(get_url(USGS_QUERY + "?" + urlencode(args)).decode("utf-8"))
    result = []
    for feat in feed.get("features", []):
        prop = feat.get("properties") or {}
        mag = prop.get("mag")
        milliseconds = prop.get("time")
        if mag is None or milliseconds is None or float(mag) < settings["min_magnitude"]:
            continue
        event_time = datetime.fromtimestamp(int(milliseconds) / 1000, UTC)
        if not current - timedelta(minutes=settings["earthquake_max_age_minutes"]) <= event_time <= current + timedelta(minutes=5):
            continue
        place = str(prop.get("place") or "한반도 인근").strip()[:78]
        link = str(prop.get("url") or "")
        if not link.startswith("https://earthquake.usgs.gov/"):
            continue
        result.append({
            "id": "usgs-" + str(feat.get("id", "unknown")),
            "kind": "earthquake",
            "title": f"한반도 인근 규모 {float(mag):.1f} 지진 발생",
            "source": "USGS",
            "published_at": iso(event_time),
            "link": link,
            "is_test": False,
        })
    return result


def make_test(mode: str, current: datetime, custom_text: str = "") -> dict:
    import uuid
    earth = mode == "test_earthquake"
    if earth:
        default = "[테스트] 한반도 인근 규모 4.3 지진 발생 (가상 상황)"
    else:
        default = "[테스트] 국회가 주요 안건 표결 예정 (가상 뉴스)"
    # Custom test text has a visible [테스트] label so it cannot be mistaken for real reporting.
    title = "[테스트] " + re.sub(r"\s+", " ", clean_title(custom_text)).strip() if custom_text else default
    return {
        "id": "test-" + uuid.uuid4().hex,
        "kind": "earthquake" if earth else "politics",
        "title": title[:160],
        "source": "방송 테스트 · 실제 뉴스 아님",
        "published_at": iso(current),
        "detected_at": iso(current),
        "link": "",
        "is_test": True,
    }


def run(mode: str = "live", custom_text: str = "") -> dict:
    settings = read_json(CONFIG_PATH, {})
    defaults = {
        "exclude_unfavorable_dem_news": True,
        "headline_max_age_minutes": 90,
        "earthquake_max_age_minutes": 90,
        "min_magnitude": 4.0,
        "earthquake_region": {"minlatitude": 31, "maxlatitude": 44,
                              "minlongitude": 123, "maxlongitude": 133},
        "active_window_minutes": 16,
        "max_news_per_run": 3,
    }
    settings = {**defaults, **settings}
    current = now_utc()
    state = read_json(STORE_PATH, {"initialized": False, "seen": {}})
    seen = state.get("seen", {}) if isinstance(state.get("seen", {}), dict) else {}
    prev = read_json(OUT_PATH, {"items": []})
    # Cross-broadcaster story history lives only inside the encrypted payload.
    old_history = prev.get("history", [])
    if not isinstance(old_history, list):
        old_history = []
    history: list[dict] = [
        entry for entry in old_history
        if isinstance(entry, dict) and isinstance(entry.get("title"), str)
        and (date := parse_date(entry.get("published_at")))
        and current - timedelta(hours=24) <= date <= current + timedelta(minutes=5)
    ][-300:]
    recent: list[dict] = []
    for old in prev.get("items", []):
        if not isinstance(old, dict) or not old.get("id") or not old.get("title"):
            continue
        when = parse_date(old.get("detected_at") or old.get("published_at"))
        # Apply safety checks to the ORIGINAL source headline, not a rewritten
        # lower-third. A concise approved headline can omit the actor, causing
        # the previously approved alert to disappear on the next refresh.
        original_title = old.get("source_title") or old.get("title", "")
        if old.get("kind") == "warning":
            if confirmed_warning_caption(original_title) != old.get("title"):
                continue
        if old.get("kind") == "politics":
            if not political_ok(original_title, block_negative=True):
                continue
            if not (old.get("is_breaking") or important_politics_news(original_title)):
                continue
        if (when and current - timedelta(minutes=settings["active_window_minutes"]) <= when <= current + timedelta(minutes=5)):
            recent.append(old)
    new = []
    failures = []
    news_source_successes = 0
    if mode.startswith("test_"):
        new.append(make_test(mode, current, custom_text))
    elif mode == "live":
        news = []
        # Query independent sources in parallel: a failing RSS URL cannot
        # delay all other sources. Each original publisher is still verified.
        requests = [(source, url) for source, url in NEWS_FEEDS.items()]
        requests += FOCUSED_FEEDS
        requests += WARNING_FEEDS
        requests += [("JTBC", JTBC_BACKUP), ("JTBC", JTBC_POLITICS_SEARCH)]
        # MBC direct feed currently delivers malformed XML; no longer block
        # the rest of collection waiting for its repeated parse failure.
        # Query USGS alongside broadcaster RSS so a slow earthquake API
        # does not add another full network timeout to the 1-minute cycle.
        with ThreadPoolExecutor(max_workers=9) as pool:
            quake_future = pool.submit(fetch_quakes, current, settings)
            futures = {
                pool.submit(fetch_rss, source, url, current, settings): (source, url)
                for source, url in requests
            }
            for future in as_completed(futures):
                source, url = futures[future]
                try:
                    news.extend(future.result())
                    news_source_successes += 1
                except Exception as exc:
                    failures.append(f"{source} feed error: {exc}")
            try:
                earthquake = quake_future.result()
            except Exception as exc:
                earthquake = []
                failures.append(f"USGS: {exc}")
        news.sort(key=lambda x: (
            int(x["kind"] == "warning"),
            int(confirmed_personnel_news(x["title"])) if x["kind"] == "politics" else 0,
            x["published_at"]
        ), reverse=True)
        candidate = news[:100] + earthquake
        candidate.sort(key=lambda x: (
            int(x["kind"] == "warning"),
            int(x["kind"] == "earthquake"),
            int(confirmed_personnel_news(x["title"])) if x["kind"] == "politics" else 0,
            x["published_at"]
        ), reverse=True)
        # Optional AI desk editor. No API key means deterministic rules only.
        # If the API fails, pause new *political* headlines for this refresh
        # rather than accidentally broadcasting unreviewed commentary.
        ai_key = os.environ.get("GEMINI_API_KEY", "").strip()
        ai_results = {}
        if ai_key:
            screening_input = []
            submitted = set()
            for x in candidate:
                if (x["kind"] != "politics" or x["id"] in seen or
                        x["id"] in submitted):
                    continue
                submitted.add(x["id"])
                screening_input.append(x)
                if len(screening_input) >= 24:
                    break
            try:
                ai_results = screen_news(
                    screening_input, api_key=ai_key,
                    model=os.environ.get("GEMINI_NEWS_MODEL", "gemini-2.5-flash-lite")
                )
                print(f"AI screening: reviewed={len(ai_results)} approved={sum(ai_results.values())}")
            except Exception as exc:
                failures.append("AI screening unavailable; political news postponed")
                print(f"AI screening unavailable ({type(exc).__name__}); political items deferred")
        else:
            print("Gemini AI inactive (GEMINI_API_KEY missing); rule-based fallback")
        politics_added = 0
        duplicate_count = 0
        for item in candidate:
            if item["id"] in seen:
                continue
            # Same event across broadcasters and across successive checks:
            # consider history within 24h, but do not deduplicate manual tests.
            duplicate = item["kind"] in ("politics", "warning") and any(
                same_story(item["title"], entry["title"])
                and (item["kind"] != "warning" or (
                    abs((parse_date(item["published_at"]) -
                         parse_date(entry["published_at"])).total_seconds()) <= 1200
                    and entry.get("kind", "politics") == "warning"
                ))
                for entry in history
            )
            if duplicate:
                seen[item["id"]] = iso(current)
                duplicate_count += 1
                continue
            if ai_key and item["kind"] == "politics":
                if item["id"] not in ai_results:
                    # Retry next refresh if AI failed or the batch was full.
                    continue
                if not ai_results[item["id"]]:
                    seen[item["id"]] = iso(current)
                    continue
            if item["kind"] == "politics" and politics_added >= settings["max_news_per_run"]:
                # Do not consume overflowed major breaking events. They will
                # be picked up by the next RSS check instead of silently lost.
                continue
            seen[item["id"]] = iso(current)
            if item["kind"] in ("politics", "warning"):
                if item["kind"] == "politics":
                    politics_added += 1
                history.append({"title": item["title"], "published_at": item["published_at"],
                                "kind": item["kind"]})
            if state.get("initialized"):
                new.append({**item, "detected_at": iso(current)})
        print(f"Selection: newly_accepted={len(new)} duplicates_omitted={duplicate_count}")
        state["initialized"] = True
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Encrypted history of actual news selected for overlay delivery.
    # This confirms publication to the viewer feed, NOT OBS output on-air.
    previous_log = prev.get("delivery_log", [])
    if not isinstance(previous_log, list):
        previous_log = []
    delivery_log = []
    for entry in previous_log:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        date = parse_date(entry.get("detected_at") or entry.get("published_at"))
        # A delivery log is an immutable audit trail of what the server selected,
        # not an RSS input feed. Never retroactively erase legitimate selected
        # headlines just because a rewritten headline no longer matches filters.
        if (date and current - timedelta(days=30) <= date <= current + timedelta(minutes=5)
                and not entry.get("is_test") and isinstance(entry.get("title"), str)):
            delivery_log.append(entry)
    logged_ids = {x["id"] for x in delivery_log}
    for item in new:
        if item.get("is_test") or item["id"] in logged_ids:
            continue
        delivery_log.append({
            "id": item["id"],
            "kind": item["kind"],
            "title": item["title"],
            "source": item["source"],
            "published_at": item["published_at"],
            "detected_at": item.get("detected_at") or iso(current),
            "link": item.get("link", ""),
            "display_seconds": 30
        })
        logged_ids.add(item["id"])
    delivery_log = delivery_log[-500:]

    # Prevent simultaneous updates from displaying duplicates; newest first.
    combined = {x["id"]: x for x in [*recent, *new]}
    active = sorted(combined.values(), key=lambda x: x.get("detected_at") or x["published_at"], reverse=True)[:20]
    cutoff = current - timedelta(days=3)
    seen = {k: t for k, t in seen.items() if (parse_date(t) or current) >= cutoff}
    state["seen"] = seen
    # Avoid commits every five minutes when nothing changed, reducing Actions usage.
    if state != read_json(STORE_PATH, {"initialized": False, "seen": {}}):
        write_json(STORE_PATH, state)
    old_items = prev.get("items", [])
    output = {
        "generated_at": iso(current) if active != old_items else prev.get("generated_at"),
        "update_interval_minutes": 1,
        "display_seconds": 30,
        "items": active,
        "history": history[-300:],
        "delivery_log": delivery_log,
        "last_check_errors": failures,
        # This heartbeat tracks a successful broadcaster request, not merely
        # an attempted workflow run. Keep it separate from last_scan_at:
        # otherwise every RSS source could fail while the dashboard looks fresh.
        "last_news_source_success_at": (
            iso(current) if mode == "live" and news_source_successes > 0 and
            (not parse_date(prev.get("last_news_source_success_at")) or
             current - parse_date(prev.get("last_news_source_success_at")) >= timedelta(minutes=15))
            else prev.get("last_news_source_success_at")
        ),
        # Persist a roughly 15-minute heartbeat even without accepted news.
        # History viewer can distinguish stale collection from an empty feed.
        "last_scan_at": (iso(current) if mode == "live" and
                         (not parse_date(prev.get("last_scan_at"))
                          or current - parse_date(prev.get("last_scan_at")) >= timedelta(minutes=15))
                         else prev.get("last_scan_at")),
        "notice": "선별 송출 서비스이며 전체 속보 목록이나 공적 경보 시스템이 아닙니다.",
    }
    if (active != old_items or output["history"] != old_history or
            delivery_log != previous_log or output["last_scan_at"] != prev.get("last_scan_at")
            or output["last_news_source_success_at"] != prev.get("last_news_source_success_at")
            or failures != prev.get("last_check_errors", [])
            or not OUT_PATH.exists()):
        write_json(OUT_PATH, output)
    if mode == "live" and not news_source_successes:
        print("WARNING All broadcaster RSS requests failed; new politics may be missing", file=sys.stderr)
    print(f"Mode {mode}. News sources OK: {news_source_successes}; Live items: {len(active)}; new items: {len(new)}; failures: {len(failures)}")
    for failure in failures:
        print("WARNING " + failure, file=sys.stderr)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=os.getenv("ALERT_MODE", "live"),
                        choices=["live", "test_politics", "test_earthquake"])
    parser.add_argument("--text", default=os.getenv("TEST_TEXT", ""))
    args = parser.parse_args()
    run(args.mode, args.text)
