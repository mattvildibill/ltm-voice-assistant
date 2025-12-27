import json
from typing import Any, Dict, List, Optional

from app.services.openai_service import client


def _ensure_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), str) else ""
    themes = _ensure_list(payload.get("themes"))
    topics = _ensure_list(payload.get("topics"))
    people = _ensure_list(payload.get("people"))
    places = _ensure_list(payload.get("places"))
    memory_chunks = _ensure_list(payload.get("memory_chunks"))

    emotions_raw = payload.get("emotions")
    emotions = emotions_raw if isinstance(emotions_raw, list) else []

    sentiment_raw = payload.get("sentiment") if isinstance(payload.get("sentiment"), dict) else {}
    sentiment_label = sentiment_raw.get("label") if sentiment_raw.get("label") in {"positive", "neutral", "negative"} else None
    sentiment_score = sentiment_raw.get("score")
    sentiment = {"label": sentiment_label, "score": sentiment_score} if sentiment_label else {}

    return {
        "summary": summary,
        "themes": themes,
        "topics": topics,
        "emotions": emotions,
        "people": people,
        "places": places,
        "sentiment": sentiment,
        "memory_chunks": memory_chunks,
    }


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except Exception:
        return None


def analyze_text(text: str) -> Dict[str, Any]:
    """
    Generates summary, themes, emotions + scores, topics, people/places,
    sentiment label/score, and memory chunks. Returns a Python dict.
    """

    system_prompt = """
    You are a personal historian and memory analyst.
    For the user's journal entry, extract the following and return STRICT JSON:

    {
      "summary": "1-2 sentence summary",
      "themes": ["...", "..."],
      "topics": ["...", "..."],
      "emotions": [{"name": "joy", "score": 0.72}, {"name": "calm", "score": 0.44}],
      "people": ["Alice", "Grandma"],
      "places": ["Paris", "home"],
      "sentiment": {"label": "positive|neutral|negative", "score": 0.0-1.0},
      "memory_chunks": ["...", "..."]
    }

    Rules:
    - Scores are between 0 and 1.
    - If a field is not applicable, return an empty list for it.
    - Sentiment label must be one of: positive, neutral, negative.
    - Do not include ANY commentary outside the JSON.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
        )
    except Exception:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        )

    raw = response.choices[0].message.content

    if raw is None:
        return _normalize_payload({})

    if not isinstance(raw, str):
        raw = str(raw)

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return _normalize_payload(parsed)
    except Exception:
        parsed = _extract_json(raw)
        if isinstance(parsed, dict):
            return _normalize_payload(parsed)

    return _normalize_payload({})
