import json
import json
from app.services.openai_service import client


def analyze_text(text: str):
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

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
    )

    raw = response.choices[0].message.content

    # Handle null or unexpected
    if raw is None:
        return {"raw": None}

    # Ensure we try to parse a string
    if not isinstance(raw, str):
        raw = str(raw)

    # Attempt JSON parsing
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}
