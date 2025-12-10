"""
Seed the API with synthetic entries (80-year-old perspective).

Usage:
  # backend must be running locally
  python scripts/seed_entries.py

This hits POST /entries so the normal pipeline (analysis, embeddings, etc.)
runs and data lands in the database. Expect OpenAI calls and associated cost.
"""

import random
import time
from typing import List

import requests

BASE_URL = "http://localhost:8000"
ENTRY_ENDPOINT = f"{BASE_URL}/entries"
TOTAL_ENTRIES = 80


def build_samples(n: int) -> List[str]:
    """Generate n short reflections in the voice of an 80-year-old."""
    eras = [
        "1940s childhood",
        "1950s teen years",
        "1960s college and early career",
        "1970s raising kids",
        "1980s career peak",
        "1990s slowing down",
        "2000s grandkids",
        "2010s retired travels",
        "2020s quieter days",
    ]
    moods = [
        "grateful",
        "nostalgic",
        "peaceful",
        "curious",
        "reflective",
        "proud",
        "bittersweet",
        "content",
    ]
    activities = [
        "morning walks",
        "family dinners",
        "old jazz records",
        "community volunteering",
        "gardening tomatoes",
        "writing letters",
        "quiet afternoons reading",
        "evening phone calls with the kids",
        "looking through photo albums",
        "cooking stews",
    ]
    lessons = [
        "the value of patience",
        "how family holds you steady",
        "that small joys matter most",
        "the importance of listening",
        "how love can soften hard years",
        "that time humbles everyone",
        "the gift of friendships that endure",
        "how resilience is built day by day",
    ]

    samples = []
    for i in range(n):
        era = random.choice(eras)
        mood = random.choice(moods)
        activity = random.choice(activities)
        lesson = random.choice(lessons)
        samples.append(
            f"At 80, thinking back to my {era}, I feel {mood}. "
            f"These days I enjoy {activity}, and I keep learning {lesson}. "
            f"I want to remember this season clearly."
        )
    return samples


def post_entry(text: str) -> None:
    resp = requests.post(ENTRY_ENDPOINT, data={"text": text})
    if not resp.ok:
        raise RuntimeError(f"Failed to create entry: {resp.status_code} {resp.text}")


def main():
    samples = build_samples(TOTAL_ENTRIES)
    for idx, text in enumerate(samples, 1):
        print(f"[{idx}/{TOTAL_ENTRIES}] posting entry...")
        post_entry(text)
        # Small delay to avoid hammering the backend/OpenAI
        time.sleep(0.2)
    print("Done seeding entries.")


if __name__ == "__main__":
    main()
