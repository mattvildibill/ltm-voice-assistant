"""
Populate the database with one year's worth of synthetic entries without
hitting OpenAI. Useful for frontend/dev work when you just need data.

Usage (run from project root with venv + .env loaded):
    python scripts/seed_fake_year.py            # add on top of existing data
    python scripts/seed_fake_year.py --wipe     # delete existing entries first
"""

import argparse
import random
from datetime import datetime, timedelta
from typing import List

from sqlmodel import delete, select

from app.db.database import get_session
from app.models.entry import Entry

DAYS = 365


def wipe_entries() -> int:
    """Delete all Entry rows and return the count removed."""
    with get_session() as session:
        existing = session.exec(select(Entry)).all()
        count = len(existing)
        session.exec(delete(Entry))
        session.commit()
        return count


def build_fake_text(day: datetime) -> tuple[str, str, List[str], str, float]:
    """Return tuple of (text, summary, topics, sentiment_label, sentiment_score)."""
    moods = ["grateful", "stressed", "content", "curious", "tired", "hopeful", "energized"]
    activities = [
        "morning walk with coffee",
        "heads-down work sprint",
        "catching up with a friend",
        "family dinner at home",
        "gym session and sauna",
        "late-night coding",
        "weekend hike in the hills",
        "reading on the couch",
        "planning the next trip",
        "trying a new recipe",
    ]
    focuses = ["health", "career", "relationships", "creativity", "finances", "learning", "mindfulness"]
    reflections = [
        "want to keep the momentum going",
        "need to slow down and rest more",
        "feeling more confident lately",
        "reminded to stay patient",
        "grateful for small wins",
        "trying to notice the good stuff",
        "want to improve consistency",
    ]

    mood = random.choice(moods)
    activity = random.choice(activities)
    focus = random.choice(focuses)
    reflection = random.choice(reflections)

    date_str = day.strftime("%Y-%m-%d")
    text = (
        f"{date_str}: Today felt {mood}. I spent time on {activity}. "
        f"My main focus was {focus}, and I {reflection}. "
        f"I want to remember this day and what felt important."
    )
    summary = f"{mood} day centered on {focus}; key moment was {activity}."
    topics = [focus, mood, "daily-reflection"]
    sentiment_label = "positive" if mood in {"grateful", "content", "hopeful", "energized"} else "neutral"
    sentiment_score = round(random.uniform(0.35, 0.9), 2)
    return text, summary, topics, sentiment_label, sentiment_score


def seed_fake_year(wipe: bool = False) -> None:
    if wipe:
        deleted = wipe_entries()
        print(f"Wiped {deleted} existing entries.")

    start_date = datetime.utcnow() - timedelta(days=DAYS)
    rows: List[Entry] = []
    for day_offset in range(DAYS):
        # randomize time of day for a more realistic timeline
        timestamp = start_date + timedelta(
            days=day_offset,
            hours=random.randint(6, 22),
            minutes=random.randint(0, 59),
        )
        text, summary, topics, sentiment_label, sentiment_score = build_fake_text(timestamp)
        word_count = len(text.split())
        rows.append(
            Entry(
                source_type="text",
                original_text=text,
                content=text,
                summary=summary,
                topics=", ".join(topics),
                word_count=word_count,
                memory_type="event",
                tags=topics,
                source="typed",
                confidence_score=0.95,
                updated_at=timestamp,
                sentiment_label=sentiment_label,
                sentiment_score=sentiment_score,
                created_at=timestamp,
            )
        )

    with get_session() as session:
        session.add_all(rows)
        session.commit()
        print(f"Inserted {len(rows)} synthetic entries spanning {DAYS} days.")


def main():
    parser = argparse.ArgumentParser(description="Seed one year of synthetic entries without OpenAI.")
    parser.add_argument("--wipe", action="store_true", help="Delete existing entries before seeding.")
    args = parser.parse_args()
    seed_fake_year(wipe=args.wipe)


if __name__ == "__main__":
    main()
