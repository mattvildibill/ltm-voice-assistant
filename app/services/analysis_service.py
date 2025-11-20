import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()  # automatically reads OPENAI_API_KEY from env


def analyze_text(text: str):
    """
    Generates summary, themes, emotions, and memory chunks.
    Returns a Python dict.
    """

    system_prompt = """
    You are a personal historian and memory analyst.
    For the user's journal entry, extract the following and return strict JSON:

    {
      "summary": "...",
      "themes": ["...", "..."],
      "emotions": ["...", "..."],
      "memory_chunks": ["...", "..."]
    }

    Do not include any commentary or explanation outside the JSON.
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
