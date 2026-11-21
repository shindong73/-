#!/usr/bin/env python3
"""Scheduled collector for the GitHub Pages OBS/PRISM breaking-news overlay.

Standard library only; use in GitHub Actions. Headlines are not independent
fact-checks. Review broadcasting permissions before public redistribution.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
STORE_PATH = ROOT / "data" / "seen.json"
OUT_PATH = ROOT / "private" / "payload.json"
CONFIG_PATH = ROOT / "config.json"
UTC = timezone.utc

# RSS feeds are retrieved server-side: mobile devices do not directly contact them.
NEWS_FEEDS = {
    "KBS": "https://news.google.com/rss/search?" + urlencode({
        "q": "site:news.kbs.co.kr 속보 when:1d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"
    }),
    "MBC": "https://news.google.com/rss/search?" + urlencode({
        "q": "site:imnews.imbc.com 속보 when:1d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"
    }),
}
USGS_QUERY = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Only explicitly breaking-news-labelled headlines are selected.
BREAKING_RE = re.compile(r"(?:\[\s*(?:긴급\s*)?속보\s*\]|\(\s*속보\s*\)|【\s*속보\s*】|^\s*속보\s*[:：])", re.I)
POLITICAL_RE = re.compile(
    r"대통령|대통령실|청와대|국회|국정|정치|여당|야당|민주당|국민의힘|조국혁신당|"
    r"국무회의|정부|총리|장관|정당|선거|대선|총선|지방선거|의원|특검|탄핵|"
    r"검찰|헌법재판소|헌재|이재명|윤석열|정청래|김민석"
)
# Conservative editorial exclusion: title-only rules have false positives and false negatives.
# The overlay must not be described as neutral or comprehensive news coverage.
DEM_ACTORS = re.compile(r"더불어민주당|민주당|이재명|정청래|김민석|대통령실|현\s*정부|집권여당")
NEGATIVE_TERMS = re.compile(
    r"압수수색|소환|구속|체포|기소|유죄|징역|실형|수사|비리|의혹|논란|"
    r"부패|뇌물|사퇴|사임|탄핵|징계|제명|고발|고소|공천|폭로|패배|"
    r"사과|파면|해임|불법|위법|선거법|벌금|기각|지지율\s*하락|폭락|위기"
)


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).astimezone(UTC)
    except (ValueError, TypeError, IndexError):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None


def get_url(url: str, *, attempts: int = 2) -> bytes:
    last_error = None
    for n in range(attempts):
        try:
            req = Request(url, headers={
                "User-Agent": "OBS-Korean-Breaking-Alerts/1.0 (+GitHub Pages; personal news monitor)",
                "Accept": "application/xml,text/xml,application/rss+xml,application/json,*/*",
            })
            with urlopen(req, timeout=18) as response:
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
    text = re.sub(r"\s*[-|]\s*(?:KBS\s*뉴스|KBS뉴스|MBC\s*뉴스|MBC뉴스|MBC)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


def political_ok(title: str, *, block_negative: bool) -> bool:
    if not BREAKING_RE.search(title) or not POLITICAL_RE.search(title):
        return False
    if block_negative and DEM_ACTORS.search(title) and NEGATIVE_TERMS.search(title):
        return False
    return True


def rewrite_headline(original: str) -> str | None:
    """Conservative, no-LLM headline restyling. Never fabricate a news event.

    When meaning-preserving rules cannot safely paraphrase, drop the article.
    Rephrasing does NOT grant redistribution rights.
    """
    title = BREAKING_RE.sub("", original, count=1).strip(" \t:：-·")
    title = re.sub(r"\s+", " ", title).strip()
    if not title or len(title) < 7 or len(title) > 82:
        return None
    if re.search(r'[“”"「」『』]', title):
        # Quotes, accusations and verbal attributions require human review.
        return None
    # Subject/object comma in journalistic telegraphese -> grammatical particle.
    match = re.fullmatch(r"([가-힣A-Za-z0-9·\s]{2,24}?),\s+(.{4,63})", title)
    if match:
        actor, action = match.groups()
        # Strict headline predicate list to avoid flipping speaker/target roles.
        if re.search(r"(발표|선포|의결|가결|통과|발의|요청|제출|소집|합의|공개|확정|승인|지시|거부|수용|제안|추진|개최|돌입|중단|복귀|결정|검토|촉구|선임|임명|해임)(?:했다|해|함|키로)?$", action):
            end = actor[-1]
            particle = '이' if '가' <= end <= '힣' and ((ord(end)-0xAC00) % 28) else '가'
            result = f"{actor}{particle} {action}"
            return result if result != title and len(result) <= 76 else None
    # Change safe word order in classic institutional headlines, without adding facts.
    match = re.fullmatch(r"(국회|국무회의|정부|대통령실)\s+(.{4,60})\s+(의결|가결|발표|확정|통과)", title)
    if match:
        institution, subject, decision = match.groups()
        result = f"{institution}에서 {subject} {decision}"
        return result if len(result) <= 76 else None
    return None


def stable_id(kind: str, link: str, title: str) -> str:
    return kind + "-" + hashlib.sha256((link or title).encode("utf-8")).hexdigest()[:24]


def fetch_rss(source: str, url: str, current: datetime, settings: dict) -> list[dict]:
    root = ET.fromstring(get_url(url))
    items = []
    for item in root.findall(".//item"):
        title = clean_title(item.findtext("title") or "")
        if not political_ok(title, block_negative=bool(settings["exclude_unfavorable_dem_news"])):
            continue
        published = parse_date(item.findtext("pubDate"))
        if not published or not (current - timedelta(minutes=settings["headline_max_age_minutes"]) <= published <= current + timedelta(minutes=5)):
            continue
        link = (item.findtext("link") or "").strip()
        # For Google News, the originating source is checked too; query terms alone aren't a permission/license.
        if source in NEWS_FEEDS:
            # Google News search is a discovery layer, not an official broadcaster RSS.
            # An explicit originating source name is required to prevent unrelated matches.
            source_name = (item.findtext("source") or "").strip().upper()
            if source not in source_name:
                continue
        if not link.startswith("https://"):
            continue
        rewritten = rewrite_headline(title)
        if not rewritten:
            continue
        items.append({
            "id": stable_id(source, link, title),
            "kind": "politics",
            "title": rewritten,
            "source": source,
            "published_at": iso(published),
            "link": link,
            "is_test": False,
        })
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
    recent: list[dict] = []
    for old in prev.get("items", []):
        when = parse_date(old.get("published_at"))
        # Preserve active events briefly across deployments for lagging clients.
        if when and current - timedelta(minutes=settings["active_window_minutes"]) <= when <= current + timedelta(minutes=5):
            recent.append(old)
    new = []
    failures = []
    if mode.startswith("test_"):
        new.append(make_test(mode, current, custom_text))
    elif mode == "live":
        news = []
        for source, url in NEWS_FEEDS.items():
            try:
                news.extend(fetch_rss(source, url, current, settings))
            except Exception as exc:
                failures.append(f"{source}: {exc}")
        try:
            earthquake = fetch_quakes(current, settings)
        except Exception as exc:
            earthquake = []
            failures.append(f"USGS: {exc}")
        # Only newest unknown politics headlines per check; all M4+ new quakes.
        news.sort(key=lambda x: x["published_at"], reverse=True)
        candidate = news[:60] + earthquake
        candidate.sort(key=lambda x: x["published_at"], reverse=True)
        politics_added = 0
        for item in candidate:
            if item["id"] in seen:
                continue
            seen[item["id"]] = iso(current)
            if item["kind"] == "politics" and politics_added >= settings["max_news_per_run"]:
                continue
            if item["kind"] == "politics":
                politics_added += 1
            if state.get("initialized"):
                new.append(item)
        state["initialized"] = True
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Prevent simultaneous updates from displaying duplicates; newest first.
    combined = {x["id"]: x for x in [*recent, *new]}
    active = sorted(combined.values(), key=lambda x: x["published_at"], reverse=True)[:20]
    cutoff = current - timedelta(days=3)
    seen = {k: t for k, t in seen.items() if (parse_date(t) or current) >= cutoff}
    state["seen"] = seen
    # Avoid commits every five minutes when nothing changed, reducing Actions usage.
    if state != read_json(STORE_PATH, {"initialized": False, "seen": {}}):
        write_json(STORE_PATH, state)
    old_items = prev.get("items", [])
    output = {
        "generated_at": iso(current) if active != old_items else prev.get("generated_at"),
        "update_interval_minutes": 5,
        "display_seconds": 30,
        "items": active,
        "last_check_errors": failures,
        "notice": "선별 송출 서비스이며 전체 속보 목록이나 공적 경보 시스템이 아닙니다.",
    }
    if active != old_items or not OUT_PATH.exists():
        write_json(OUT_PATH, output)
    print(f"Mode {mode}. Live items: {len(active)}; new items: {len(new)}; failures: {len(failures)}")
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
