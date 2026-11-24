"""Optional LLM editorial gate for verified South Korean breaking-news headlines.

The collector remains operational without GEMINI_API_KEY, using its deterministic
filters. With a key, this gate verifies whether an already selected headline
reports a substantive *event* rather than a political quotation or reaction.
The gate cannot verify real-world truth from an RSS headline alone.
"""
from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash-lite"

INSTRUCTIONS = """You are a careful Korean TV breaking-news desk editor.
Decide whether each supplied item is an important, concrete South Korean
political or government news EVENT that should go to a breaking-news ticker.
Use only the supplied headline and publisher. Do not invent details.
Apply these same editorial standards to every party, regardless of ideology.
Approve: an actual national cabinet minister's/vice-minister's stated
resignation; an appointment/dismissal of a nationally significant official;
enacted/definitively passed laws, major court rulings, national election
results, or an urgent concrete government/parliamentary decision.
Reject every National Election Commission (선관위, 선거관리위원회) story
and claims or controversies about 부정선거, vote/count manipulation,
even if a related arrest, ruling or announcement took place.
Reject routine personnel moves at provincial, city, county, municipal,
subordinate or regional special-purpose agencies (for example:
울산시 울산경제자유구역청장 해임).
The issue must have clear national significance.
Reject: a party's opinion, reaction, criticism, counterstatement, press
commentary, a quoted slogan, a resignation DEMAND rather than the resignation
itself, a vague forecast, rumors, and routine press conferences or visits.
Explicit [속보]/[긴급] labels never by themselves make commentary important.
If a statement is attributed to '국힘', '국민의힘', '민주당', etc., and describes
that party's evaluation rather than an event, REJECT.
For example:
- 국힘 "수능마저 못 믿는 나라…최교진 사퇴로 끝날 일 아냐" -> reject.
- 최교진 교육부 장관, 사의 표명 -> approve.
- 정청래 "정부 발표 유감" -> reject.
- 국회, 예산안 최종 가결 -> approve.
- 교육부 장관 사퇴 요구 -> reject.
- 정부, 신임 장관 임명 공식 발표 -> approve.
Reject when ambiguous rather than confidently claiming an event happened.
Return one Boolean decision and a brief Korean reason per item, preserving IDs.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "approve": {"type": "boolean"},
                    "reason": {"type": "string"}
                },
                "required": ["id", "approve", "reason"],
                "additionalProperties": False
            }
        }
    },
    "required": ["items"],
    "additionalProperties": False
}


def parse_decisions(result: dict, expected_ids: list[str]) -> dict[str, bool]:
    """Validate an entire Gemini batch; uncertain/incomplete output is rejected."""
    if not isinstance(result, dict) or result.get("promptFeedback", {}).get("blockReason"):
        raise ValueError("Blocked or invalid Gemini response")
    candidates = result.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise ValueError("Expected exactly one Gemini candidate")
    candidate = candidates[0]
    if candidate.get("finishReason") != "STOP":
        raise ValueError("Gemini did not finish response")
    parts = candidate.get("content", {}).get("parts", [])
    if not isinstance(parts, list):
        raise ValueError("Invalid Gemini parts")
    content = "".join(
        p["text"] for p in parts
        if isinstance(p, dict) and isinstance(p.get("text"), str) and not p.get("thought")
    )
    rows = json.loads(content).get("items")
    if not isinstance(rows, list) or len(rows) != len(expected_ids):
        raise ValueError("Gemini returned missing or additional decisions")
    decisions = {}
    for row in rows:
        if (not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not isinstance(row.get("approve"), bool)
                or not isinstance(row.get("reason"), str)
                or row["id"] in decisions):
            raise ValueError("Malformed or duplicate Gemini decision")
        decisions[row["id"]] = row["approve"]
    if set(decisions) != set(expected_ids):
        raise ValueError("Gemini invented or omitted article IDs")
    return decisions


def screen_news(items: list[dict], *, api_key: str, model: str = DEFAULT_MODEL) -> dict[str, bool]:
    """Send at most 24 verified publisher titles through Gemini in one request."""
    if not items:
        return {}
    if not api_key.strip():
        raise ValueError("GEMINI_API_KEY is missing")
    if len(items) > 24:
        raise ValueError("Gemini screening batch too large")
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,100}", model):
        raise ValueError("Invalid Gemini model identifier")
    expected_ids = [x["id"] for x in items]
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("Duplicated Gemini article IDs")
    body = {
        "systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps([
            {"id": x["id"], "title": x.get("source_title") or x["title"], "source": x["source"]}
            for x in items
        ], ensure_ascii=False)}]}],
        "generationConfig": {
            "candidateCount": 1,
            "temperature": 0,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
            "responseJsonSchema": SCHEMA
        }
    }
    req = Request(
        f"{ENDPOINT}/{model}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        method="POST"
    )
    with urlopen(req, timeout=22) as response:
        result = json.load(response)
    return parse_decisions(result, expected_ids)
