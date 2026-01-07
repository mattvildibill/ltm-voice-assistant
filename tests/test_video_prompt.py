from datetime import datetime, timedelta

from app.models.entry import Entry, MemoryType
from app.services import video_prompt


def make_entry(entry_id: str, summary: str, created_at: datetime):
    entry = Entry(
        id=entry_id,
        user_id="u",
        memory_type=MemoryType.EVENT,
        source_type="text",
        original_text=summary or "text",
        content=summary or "text",
        created_at=created_at,
        updated_at=created_at,
    )
    entry.summary = summary
    entry.word_count = len((summary or "").split())
    return entry


def test_candidate_selection_dedupes():
    now = datetime.utcnow()
    entry1 = make_entry(
        "e1",
        "Hiking at sunset and feeling proud about a promotion.",
        now - timedelta(days=2),
    )
    entry2 = make_entry(
        "e2",
        "Walking along the beach at sunset with neon lights.",
        now - timedelta(days=3),
    )
    entry3 = make_entry(
        "e3",
        "Got a job offer and felt grateful.",
        now - timedelta(days=1),
    )

    significant, cinematic = video_prompt.select_candidates(
        [entry1, entry2, entry3], top_n=2, now=now
    )

    sig_ids = {item.entry.id for item in significant}
    cin_ids = {item.entry.id for item in cinematic}

    assert sig_ids.isdisjoint(cin_ids)
    assert "e1" in sig_ids
    assert "e2" in cin_ids


def test_build_prompt_redacts_names_and_counts_shots():
    now = datetime.utcnow()
    entry1 = make_entry("e1", "Went hiking with Alex at sunset.", now)
    entry1.people = "Alex"
    entry2 = make_entry("e2", "Cooked dinner with my mom.", now - timedelta(days=1))
    entry2.people = "Mom"

    result = video_prompt.build_sora_prompt(
        [entry1, entry2],
        duration_seconds=15,
        orientation="landscape",
        style="cinematic_realistic",
        preset="family_highlight_reel",
    )

    assert result.redactions["names_removed"] is True
    assert "Alex" not in result.prompt
    assert "15s" in result.prompt
    assert "1280x720 landscape" in result.prompt
    assert "No narration" in result.prompt
    assert len(result.shots) == 3
