"""Optional LLM editorial gate for verified South Korean breaking-news headlines.

The collector remains operational without OPENAI_API_KEY, using its deterministic
filters. With a key, this gate verifies whether an already selected headline
reports a substantive *event* rather than a political quotation or reaction.
The gate cannot verify real-world truth from an RSS headline alone.
"""
from __future__ import annotations

import json
from urllib.request import Request, urlopen

ENDPOINT = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6-luna"

INSTRUCTIONS = """You are a careful Korean TV breaking-news desk editor.
Decide whether each supplied item is an important, concrete South Korean
political or government news EVENT that should go to a breaking-news ticker.
Use only the supplied headline and publisher. Do not invent details.
Apply these same editorial standards to every party, regardless of ideology.
Approve: an actual government minister's/official's stated resignation;
appointment, dismissal or confirmation of a high official; enacted/definitively
passed laws, major court rulings, election results, or an urgent concrete
government or parliamentary decision clearly reported as occurring.
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
    """Fail closed on partial, malformed, duplicated, or contradictory output."""
    if result.get("status") != "completed":
        raise ValueError("AI response did not complete")
    text_parts = [
        block.get("text", "")
        for message in result.get("output", [])
        if message.get("type") == "message"
        for block in message.get("content", [])
        if block.get("type") == "output_text"
    ]
    payload = json.loads("".join(text_parts))
    rows = payload["items"]
    if not isinstance(rows, list) or len(rows) != len(expected_ids):
        raise ValueError("AI output count mismatch")
    out = {}
    for row in rows:
        if (not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not isinstance(row.get("approve"), bool)
                or row["id"] in out):
            raise ValueError("Malformed or duplicate AI decision")
        out[row["id"]] = row["approve"]
    if set(out) != set(expected_ids):
        raise ValueError("AI output IDs mismatch")
    return out


def screen_news(items: list[dict], *, api_key: str, model: str = DEFAULT_MODEL) -> dict[str, bool]:
    """Inspect up to 24 already-vetted headlines in one inexpensive API call."""
    if not items:
        return {}
    if not api_key.strip():
        raise ValueError("OPENAI_API_KEY must be set for AI screening")
    if len(items) > 24:
        raise ValueError("Too many candidate items in one AI request")
    request = {
        "model": model,
        "store": False,
        "max_output_tokens": 1200,
        "instructions": INSTRUCTIONS,
        "input": json.dumps(
            [{"id": x["id"], "title": x["title"], "source": x["source"]}
             for x in items],
            ensure_ascii=False
        ),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "breaking_news_gate",
                "strict": True,
                "schema": SCHEMA
            }
        }
    }
    req = Request(
        ENDPOINT,
        data=json.dumps(request, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json"
        },
        method="POST"
    )
    with urlopen(req, timeout=22) as response:
        result = json.load(response)
    return parse_decisions(result, [x["id"] for x in items])
