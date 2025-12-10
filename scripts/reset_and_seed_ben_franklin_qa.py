"""
Destructive seeding script for local testing only.
- Wipes all existing entries from the DB.
- Generates Benjamin Franklin Q&A entries via OpenAI.
- Pipes each generated Q&A through the normal entry pipeline (process_entry) so summaries,
  sentiment, embeddings, etc. are created as usual.

Run from project root with venv + .env configured:
    python scripts/reset_and_seed_ben_franklin_qa.py
"""

import asyncio
import json
from typing import Optional

from sqlmodel import delete, select

from app.db.database import get_session
from app.models.entry import Entry
from app.services.entry_service import process_entry
from app.services.openai_service import client

TARGET_COUNT = 1000


def wipe_entries() -> int:
    """Delete all Entry rows. Returns number removed."""
    with get_session() as session:
        existing = session.exec(select(Entry)).all()
        count = len(existing)
        session.exec(delete(Entry))
        session.commit()
        return count


def generate_bf_qa_text() -> Optional[str]:
    """
    Ask OpenAI for one Benjamin Franklin Q&A in JSON.
    Returns formatted text: \"Q: ...\\nA: ...\" or None on failure.
    """
    prompt = (
        "Generate one factual question and answer about Benjamin Franklin. "
        "Return strict JSON with keys 'question' and 'answer'."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        content = resp.choices[0].message.content if resp.choices else None
        if not content:
            return None
        data = json.loads(content)
        q = data.get("question")
        a = data.get("answer")
        if q and a:
            return f"Q: {q}\nA: {a}"
    except Exception:
        return None
    return None


async def seed_entries(count: int) -> int:
    """Generate and store count entries via process_entry. Returns successful count."""
    success = 0
    for i in range(count):
        qa_text = generate_bf_qa_text()
        if not qa_text:
            continue
        try:
            await process_entry(text=qa_text, file=None)
            success += 1
        except Exception:
            # Skip failures and continue
            continue
    return success


async def main():
    deleted = wipe_entries()
    print(f"Deleted {deleted} existing entries.")
    inserted = await seed_entries(TARGET_COUNT)
    print(f"Seeded {inserted} Benjamin Franklin Q&A entries.")


if __name__ == "__main__":
    asyncio.run(main())
