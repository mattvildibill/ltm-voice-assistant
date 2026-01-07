from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.models.entry import Entry

SIGNIFICANT_KEYWORDS = {
    "wedding",
    "graduation",
    "job",
    "promotion",
    "offer",
    "interview",
    "move",
    "moving",
    "relocation",
    "family",
    "mom",
    "dad",
    "mother",
    "father",
    "parent",
    "parents",
    "child",
    "kids",
    "baby",
    "birth",
    "loss",
    "grief",
    "funeral",
    "engaged",
    "engagement",
    "married",
    "divorce",
    "breakup",
    "illness",
    "health",
    "diagnosis",
    "hospital",
    "graduated",
    "anniversary",
    "milestone",
    "goal",
}

EMOTION_KEYWORDS = {
    "proud",
    "grateful",
    "excited",
    "thrilled",
    "anxious",
    "nervous",
    "heartbroken",
    "sad",
    "stress",
    "stressed",
    "love",
    "joy",
    "angry",
    "overwhelmed",
    "relieved",
    "hopeful",
}

TIME_OF_DAY = {
    "sunrise",
    "morning",
    "noon",
    "afternoon",
    "sunset",
    "dusk",
    "night",
    "midnight",
    "evening",
}

WEATHER_WORDS = {
    "rain",
    "rainy",
    "storm",
    "stormy",
    "snow",
    "snowy",
    "fog",
    "foggy",
    "windy",
    "breezy",
    "cloudy",
    "sunny",
}

PLACE_WORDS = {
    "beach",
    "mountain",
    "mountains",
    "city",
    "downtown",
    "park",
    "trail",
    "forest",
    "kitchen",
    "home",
    "street",
    "road",
    "cafe",
    "restaurant",
    "concert",
    "studio",
    "office",
    "lake",
    "river",
    "camp",
    "cabin",
    "airport",
    "train",
    "bus",
    "gym",
}

MOTION_WORDS = {
    "walking",
    "running",
    "driving",
    "biking",
    "cycling",
    "hiking",
    "cooking",
    "dancing",
    "singing",
    "laughing",
    "traveling",
    "travelling",
    "swimming",
    "skiing",
    "climbing",
    "reading",
    "writing",
    "working",
    "building",
    "painting",
    "filming",
}

SENSORY_WORDS = {
    "warm",
    "glowing",
    "neon",
    "quiet",
    "crowded",
    "soft",
    "gentle",
    "bright",
    "golden",
    "rainy",
    "hazy",
    "shimmering",
    "dusty",
    "crisp",
    "moody",
}

STYLE_PROFILES = {
    "cinematic_realistic": {
        "label": "cinematic realistic",
        "tone": "natural light, crisp detail, subtle film grain",
        "camera": [
            "slow push-in",
            "gentle pan",
            "handheld drift",
            "locked-off frame",
            "slow tilt",
            "dolly past",
        ],
    },
    "dreamy_soft_film": {
        "label": "dreamy soft film",
        "tone": "soft haze, pastel highlights, warm bloom",
        "camera": [
            "floating glide",
            "slow push-in",
            "soft focus rack",
            "gentle handheld sway",
            "static wide",
            "subtle tilt",
        ],
    },
    "documentary_handheld": {
        "label": "documentary handheld",
        "tone": "natural contrast, textured grain, observational feel",
        "camera": [
            "handheld follow",
            "quick pan",
            "steady close-up",
            "wide establishing",
            "shoulder-level tracking",
            "locked-off detail",
        ],
    },
}

PRESET_PROFILES = {
    "none": "balanced everyday moments",
    "family_highlight_reel": "family warmth, connection, shared rituals",
    "adventure_montage": "adventurous energy, movement, outdoor scenes",
    "calm_reflective": "quiet, reflective mood, gentle pacing",
    "celebration_moments": "joyful milestones, celebratory energy",
}

ORIENTATION_PRESETS = {
    "landscape": "1280x720 landscape",
    "portrait": "720x1280 portrait",
}

ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9]+(?:\s+[A-Za-z0-9]+){0,3}\s+(?:st|street|ave|avenue|rd|road|blvd|boulevard|ln|lane|dr|drive|ct|court|way|trail|trl)\b",
    re.IGNORECASE,
)
PHONE_PATTERN = re.compile(
    r"\b(?:\+?\d{1,2}[\s-]?)?(?:\(\d{3}\)|\d{3})[\s-]?\d{3}[\s-]?\d{4}\b",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class CandidateScore:
    entry: Entry
    significance_score: float
    cinematic_score: float


@dataclass
class Shot:
    shot: int
    description: str
    source_entry_ids: List[str]


@dataclass
class PromptBuildResult:
    prompt: str
    shots: List[Shot]
    used_entry_ids: List[str]
    redactions: Dict[str, bool]
    debug: Dict[str, List[Dict[str, float]]]


def _safe_float(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _listify(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            if isinstance(loaded, list):
                return [str(v).strip() for v in loaded if str(v).strip()]
        except Exception:
            pass
    return _split(value if isinstance(value, str) else str(value))


def _entry_text(entry: Entry) -> str:
    return (
        getattr(entry, "summary", None)
        or getattr(entry, "title", None)
        or getattr(entry, "content", None)
        or getattr(entry, "original_text", None)
        or ""
    ).strip()


def _entry_context(entry: Entry) -> str:
    pieces = [
        getattr(entry, "summary", None),
        getattr(entry, "title", None),
        getattr(entry, "content", None),
        getattr(entry, "original_text", None),
        getattr(entry, "themes", None),
        getattr(entry, "topics", None),
        getattr(entry, "emotions", None),
        getattr(entry, "people", None),
        getattr(entry, "places", None),
    ]
    return " ".join([str(piece) for piece in pieces if piece]).lower()


def _preview_text(entry: Entry, limit: int = 120) -> str:
    text = _entry_text(entry)
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _truncate_text(text: str, limit: int) -> str:
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _word_count(entry: Entry) -> int:
    count = getattr(entry, "word_count", None)
    if isinstance(count, int) and count > 0:
        return count
    text = _entry_text(entry)
    return len(text.split()) if text else 0


def _recency_boost(entry: Entry, now: datetime, window_days: int = 180) -> float:
    created = getattr(entry, "created_at", None) or now
    age_days = max(0.0, (now - created).total_seconds() / 86400.0)
    if window_days <= 0:
        return 0.0
    return max(0.0, 1.0 - (age_days / float(window_days)))


def _count_keywords(text: str, keywords: Iterable[str]) -> int:
    if not text:
        return 0
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword in lowered)


def _emotion_intensity(entry: Entry, text: str) -> float:
    sentiment = _safe_float(getattr(entry, "sentiment_score", None))
    if sentiment is not None:
        return min(1.0, abs(sentiment))

    emotion_scores_raw = getattr(entry, "emotion_scores", None)
    if emotion_scores_raw:
        try:
            data = json.loads(emotion_scores_raw)
            if isinstance(data, dict) and data:
                return min(1.0, max(abs(_safe_float(v) or 0.0) for v in data.values()))
        except Exception:
            pass

    emotions = _split(getattr(entry, "emotions", None))
    if emotions:
        return 0.4

    return 0.35 if _count_keywords(text, EMOTION_KEYWORDS) else 0.0


def _life_event_bonus(text: str, tags: Sequence[str]) -> float:
    hits = _count_keywords(text, SIGNIFICANT_KEYWORDS)
    tag_hits = sum(1 for tag in tags if tag.lower() in SIGNIFICANT_KEYWORDS)
    total_hits = hits + tag_hits
    if total_hits <= 0:
        return 0.0
    return min(0.4, 0.1 * total_hits)


def _scene_score(text: str, places: Sequence[str]) -> float:
    hits = _count_keywords(text, TIME_OF_DAY | WEATHER_WORDS | PLACE_WORDS)
    place_bonus = 0.2 if places else 0.0
    return min(1.0, 0.1 * hits + place_bonus)


def _sensory_score(text: str) -> float:
    hits = _count_keywords(text, SENSORY_WORDS)
    return min(1.0, 0.12 * hits)


def _motion_score(text: str) -> float:
    hits = _count_keywords(text, MOTION_WORDS)
    return min(1.0, 0.12 * hits)


def _structure_score(text: str) -> float:
    if not text:
        return 0.0
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if 1 <= len(sentences) <= 2:
        return 0.2
    if len(sentences) > 2:
        return 0.1
    return 0.0


def score_entries(entries: Sequence[Entry], now: Optional[datetime] = None) -> List[CandidateScore]:
    now = now or datetime.utcnow()
    max_length = max((_word_count(entry) for entry in entries), default=1)

    scored: List[CandidateScore] = []
    for entry in entries:
        text = _entry_context(entry)
        length_score = min(1.0, (_word_count(entry) / float(max_length)) if max_length else 0.0)
        emotion_score = _emotion_intensity(entry, text)
        tags = _listify(getattr(entry, "tags", None)) + _split(getattr(entry, "topics", None))
        life_bonus = _life_event_bonus(text, tags)
        recency = _recency_boost(entry, now)
        significance = (0.35 * length_score) + (0.3 * emotion_score) + (0.2 * life_bonus) + (0.15 * recency)

        places = _split(getattr(entry, "places", None))
        scene = _scene_score(text, places)
        sensory = _sensory_score(text)
        motion = _motion_score(text)
        structure = _structure_score(text)
        cinematic = (0.35 * scene) + (0.25 * sensory) + (0.2 * motion) + (0.1 * structure) + (0.1 * recency)

        scored.append(
            CandidateScore(
                entry=entry,
                significance_score=min(1.0, significance),
                cinematic_score=min(1.0, cinematic),
            )
        )
    return scored


def select_candidates(
    entries: Sequence[Entry],
    top_n: int = 5,
    now: Optional[datetime] = None,
) -> Tuple[List[CandidateScore], List[CandidateScore]]:
    scored = score_entries(entries, now=now)

    def sort_key(item: CandidateScore, attr: str) -> Tuple[float, datetime, str]:
        created_at = getattr(item.entry, "created_at", None) or datetime.min
        score = getattr(item, attr)
        return (score, created_at, item.entry.id)

    significant_sorted = sorted(scored, key=lambda s: sort_key(s, "significance_score"), reverse=True)
    significant = significant_sorted[:top_n]
    significant_ids = {item.entry.id for item in significant}

    cinematic_sorted = sorted(scored, key=lambda s: sort_key(s, "cinematic_score"), reverse=True)
    cinematic = [item for item in cinematic_sorted if item.entry.id not in significant_ids][:top_n]

    return significant, cinematic


def _sanitize_entry_text(text: str) -> str:
    if not text:
        return ""
    sanitized = text.strip()
    sanitized = re.sub(r"^(today\s+)?i\s+", "", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"^i\s+", "", sanitized, flags=re.IGNORECASE)
    return sanitized


def _redact_sensitive(text: str, people: Sequence[str]) -> Tuple[str, bool]:
    if not text:
        return "", False

    redacted = text
    names_removed = False

    for person in people:
        person_name = person.strip()
        if not person_name:
            continue
        lower_name = person_name.lower()
        if "mom" in lower_name or "mother" in lower_name:
            replacement = "my mom"
        elif "dad" in lower_name or "father" in lower_name:
            replacement = "my dad"
        elif "wife" in lower_name or "husband" in lower_name or "partner" in lower_name:
            replacement = "my partner"
        elif "boss" in lower_name or "manager" in lower_name:
            replacement = "my manager"
        elif "cowork" in lower_name:
            replacement = "my coworker"
        else:
            replacement = "a friend"
        pattern = re.compile(re.escape(person_name), re.IGNORECASE)
        if pattern.search(redacted):
            redacted = pattern.sub(replacement, redacted)
            names_removed = True

    if EMAIL_PATTERN.search(redacted):
        redacted = EMAIL_PATTERN.sub("an email", redacted)
        names_removed = True

    if PHONE_PATTERN.search(redacted):
        redacted = PHONE_PATTERN.sub("a phone number", redacted)
        names_removed = True

    if ADDRESS_PATTERN.search(redacted):
        redacted = ADDRESS_PATTERN.sub("a nearby street", redacted)
        names_removed = True

    return redacted, names_removed


def _extract_scene_cues(text: str) -> str:
    if not text:
        return ""
    lowered = text.lower()
    cues = []
    time_hit = next((word for word in TIME_OF_DAY if word in lowered), None)
    weather_hit = next((word for word in WEATHER_WORDS if word in lowered), None)
    place_hit = next((word for word in PLACE_WORDS if word in lowered), None)
    motion_hit = next((word for word in MOTION_WORDS if word in lowered), None)

    if time_hit:
        cues.append(f"at {time_hit}")
    if weather_hit:
        cues.append(f"in {weather_hit} weather")
    if place_hit:
        cues.append(f"near the {place_hit}")
    if motion_hit:
        cues.append(f"with {motion_hit} motion")

    return " ".join(cues)


def _build_shots(entries: Sequence[Entry], shot_count: int, style_key: str) -> Tuple[List[Shot], bool]:
    profile = STYLE_PROFILES.get(style_key, STYLE_PROFILES["cinematic_realistic"])
    camera_cues = profile["camera"]
    shots: List[Shot] = []
    names_removed = False

    for idx in range(shot_count):
        entry = entries[idx % len(entries)]
        entry_text = _sanitize_entry_text(_entry_text(entry))
        people = _split(getattr(entry, "people", None))
        entry_text, redacted = _redact_sensitive(entry_text, people)
        names_removed = names_removed or redacted

        if entry_text:
            entry_text = _truncate_text(entry_text, limit=140)
            entry_text = _sanitize_entry_text(entry_text)
            entry_text, redacted_again = _redact_sensitive(entry_text, people)
            names_removed = names_removed or redacted_again
        else:
            entry_text = "a quiet everyday moment"

        cues = _extract_scene_cues(entry_text)
        cue_text = f" {cues}" if cues else ""
        lead = "A grounded scene" if style_key == "cinematic_realistic" else "A moment"
        description = f"{lead}{cue_text} showing {entry_text}."
        camera = camera_cues[idx % len(camera_cues)]
        description = f"{description} {camera.capitalize()}."

        shots.append(
            Shot(
                shot=idx + 1,
                description=description,
                source_entry_ids=[entry.id],
            )
        )

    return shots, names_removed


def _shot_count(memory_count: int) -> int:
    if memory_count <= 2:
        return 3
    if memory_count <= 3:
        return 4
    if memory_count <= 5:
        return 5
    if memory_count <= 8:
        return 5
    return 6


def build_sora_prompt(
    entries: Sequence[Entry],
    duration_seconds: int,
    orientation: str,
    style: str,
    preset: Optional[str] = None,
) -> PromptBuildResult:
    if not entries:
        raise ValueError("No entries provided.")

    profile = STYLE_PROFILES.get(style, STYLE_PROFILES["cinematic_realistic"])
    preset_key = preset or "none"
    preset_desc = PRESET_PROFILES.get(preset_key, PRESET_PROFILES["none"])
    orientation_desc = ORIENTATION_PRESETS.get(orientation, ORIENTATION_PRESETS["landscape"])

    shot_count = _shot_count(len(entries))
    shots, names_removed = _build_shots(entries, shot_count, style)

    montage_line = f"{shot_count}-shot montage"
    tone_line = f"Style: {profile['label']} - {profile['tone']}."
    theme_line = f"Theme: {preset_desc}." if preset_desc else ""

    prompt_lines = [
        f"Create a {duration_seconds}s, {orientation_desc} video.",
        f"Structure: {montage_line}.",
        tone_line,
    ]
    if theme_line:
        prompt_lines.append(theme_line)
    prompt_lines.extend(
        [
            "Camera motion is subtle and cinematic, no aggressive shakes.",
            "No narration, ambient sound only. Avoid text overlays.",
            "Shots:",
        ]
    )

    prompt_lines.extend([f"{shot.shot}. {shot.description}" for shot in shots])

    debug_entries = []
    scored = score_entries(entries)
    for item in scored:
        debug_entries.append(
            {
                "entry_id": item.entry.id,
                "significance_score": item.significance_score,
                "cinematic_score": item.cinematic_score,
            }
        )

    return PromptBuildResult(
        prompt="\n".join(prompt_lines).strip(),
        shots=shots,
        used_entry_ids=[entry.id for entry in entries],
        redactions={"names_removed": names_removed},
        debug={"entry_scores": debug_entries},
    )


def build_candidate_payload(candidate: CandidateScore, tag: str) -> Dict:
    return {
        "id": candidate.entry.id,
        "created_at": candidate.entry.created_at,
        "summary": getattr(candidate.entry, "summary", None),
        "content": getattr(candidate.entry, "content", None) or getattr(candidate.entry, "original_text", None),
        "preview": _preview_text(candidate.entry, limit=120),
        "score": candidate.significance_score if tag == "significant" else candidate.cinematic_score,
    }


def filter_recent_entries(entries: Sequence[Entry], now: Optional[datetime] = None) -> List[Entry]:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=180)
    recent = [entry for entry in entries if (getattr(entry, "created_at", None) or now) >= cutoff]
    return recent
