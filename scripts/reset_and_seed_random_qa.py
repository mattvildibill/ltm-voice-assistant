"""
Destructive seeding script for local testing only.
- Optionally wipes all existing entries from the DB.
- Seeds story-forward prompt/answer pairs so the UI has rich content.
- Optional OpenAI mode generates a coherent, single-person year of entries.

Usage (run from project root with venv + .env loaded):
    python scripts/reset_and_seed_random_qa.py --wipe --count 500 --days 365
    python scripts/reset_and_seed_random_qa.py --wipe --count 365 --days 365 --openai
"""

import argparse
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Ensure project root is on the import path when running as a script
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
from sqlmodel import delete, select

load_dotenv(ROOT_DIR / ".env")

from app.db.database import get_session, init_db, migrate_db
from app.models.entry import Entry, MemoryType, SourceType
from app.services.openai_service import client
from app.services.embedding_service import embed_text, serialize_embedding

OPENAI_MODEL = "gpt-4o-mini"
RECENT_CONTEXT_LIMIT = 6
CONTINUITY_LIMIT = 16

PROMPTS: List[Dict[str, object]] = [
    {
        "prompt": (
            "Tell me about a time you surprised yourself. Not a small win--pick a moment "
            "where you realized you were capable of more than you thought. Set the scene, "
            "what you were feeling going in, what happened, and what you carried forward from it."
        ),
        "topic": "self_surprise",
        "memory_type": MemoryType.IDENTITY,
    },
    {
        "prompt": (
            "Tell the story of a family tradition that mattered. Describe where it happened, "
            "the smells and sounds, who was there, and what it taught you about the people you came from."
        ),
        "topic": "family_tradition",
        "memory_type": MemoryType.REFLECTION,
    },
    {
        "prompt": (
            "Tell me about a season of life that was difficult but meaningful. Do not rush to the lesson. "
            "Spend time in the middle: what it felt like day to day, what you were afraid of, and what slowly changed."
        ),
        "topic": "hard_season",
        "memory_type": MemoryType.REFLECTION,
    },
    {
        "prompt": (
            "Tell me about a moment that seemed ordinary at the time but became precious later. "
            "Describe it like a scene from a movie--what you saw, heard, and felt--and why it matters now."
        ),
        "topic": "small_moment",
        "memory_type": MemoryType.REFLECTION,
    },
    {
        "prompt": (
            "Tell me about a piece of advice you received that still echoes. Who said it, what was happening "
            "around that moment, and how has it shaped the way you live?"
        ),
        "topic": "advice_echo",
        "memory_type": MemoryType.IDENTITY,
    },
    {
        "prompt": "Tell the story of a place from childhood that you still carry with you.",
        "topic": "childhood_place",
        "memory_type": MemoryType.EVENT,
    },
    {
        "prompt": "Describe a turning point in your career or work life and how it changed your direction.",
        "topic": "career_turn",
        "memory_type": MemoryType.PROJECT,
    },
    {
        "prompt": "Tell me about a friendship that changed shape over time and what you learned from it.",
        "topic": "friendship_shift",
        "memory_type": MemoryType.REFLECTION,
    },
    {
        "prompt": "Tell the story of a goodbye you still think about.",
        "topic": "goodbye",
        "memory_type": MemoryType.EVENT,
    },
    {
        "prompt": "Share a time someone showed you unexpected kindness and why it mattered.",
        "topic": "unexpected_kindness",
        "memory_type": MemoryType.REFLECTION,
    },
    {
        "prompt": "Describe an object you have kept and the memory it holds.",
        "topic": "object_kept",
        "memory_type": MemoryType.EVENT,
    },
    {
        "prompt": "Tell me about a promise you made to yourself and how it has held up over time.",
        "topic": "promise_to_self",
        "memory_type": MemoryType.IDENTITY,
    },
    {
        "prompt": "Tell me about a small celebration that meant more than it looked like.",
        "topic": "small_celebration",
        "memory_type": MemoryType.EVENT,
    },
    {
        "prompt": "Describe a failure that later turned into a quiet success in your life.",
        "topic": "failure_reframe",
        "memory_type": MemoryType.REFLECTION,
    },
    {
        "prompt": "Tell me about a moment you felt like you truly belonged.",
        "topic": "belonging",
        "memory_type": MemoryType.IDENTITY,
    },
    {
        "prompt": "Share a travel memory that still feels vivid and why it stays with you.",
        "topic": "travel_scene",
        "memory_type": MemoryType.EVENT,
    },
    {
        "prompt": "Tell the story of a quiet morning or evening that helped you reset.",
        "topic": "quiet_reset",
        "memory_type": MemoryType.REFLECTION,
    },
    {
        "prompt": "Tell me about a moment you realized what love looks like in practice.",
        "topic": "love_in_practice",
        "memory_type": MemoryType.REFLECTION,
    },
    {
        "prompt": "Describe a moment you decided to change something important in your life.",
        "topic": "decision_change",
        "memory_type": MemoryType.REFLECTION,
    },
]

ANSWER_TEMPLATES: Dict[str, List[str]] = {
    "self_surprise": [
        (
            "I still remember {time_of_day} at {place}, when I agreed to {decision} even though I felt {fear}. "
            "The room felt too quiet, the kind of quiet that makes you hear your own heartbeat, and I was sure I would stumble. "
            "But then {change}, and I realized I could actually do it, not perfectly, but honestly. "
            "By the end I was not trying to impress anyone; I was just doing the work. "
            "What stayed with me was a calm kind of pride that said {lesson}."
        ),
        (
            "It was {season}, {time_of_day}, and the light at {place} made everything feel sharper. "
            "I had said yes to something I was not ready for, mostly because I was tired of being the person who stayed safe. "
            "I felt {fear} and almost backed out, but I did the next small step anyway. "
            "Somewhere in the middle, I surprised myself by staying present, and that was the real win. "
            "I carried forward the idea that {lesson}."
        ),
    ],
    "family_tradition": [
        (
            "Our tradition lived in ordinary places, usually {place}, with {smell} in the air and {sound} in the background. "
            "{person_role} would always show up early, and {second_person_role} would pretend not to care but somehow lead the rhythm. "
            "I used to think the tradition was the food, but it was really the choreography of care, the way we made room for each other. "
            "It taught me that {value} is not a speech; it is a habit you repeat until it becomes a home."
        ),
        (
            "We called it {ritual}, but it was really just the way we kept showing up. "
            "The smells of {smell} and the clatter of {sound} felt like a clock starting. "
            "Even when we disagreed, there was a tenderness underneath it, a reminder that you belonged. "
            "That tradition taught me that {value} can be practical, quiet, and steady."
        ),
    ],
    "hard_season": [
        (
            "That season did not announce itself. It was more like waking up and realizing everything required extra effort. "
            "I was afraid of {fear}, and the days blurred together while I tried to keep up with the basics. "
            "The change was not one big moment; it was {change}, then another small step, then another. "
            "Looking back, the lesson was not about toughness. It was about learning that {lesson}."
        ),
        (
            "In the middle of it, the world felt smaller. My routines shrank to {activity}, short walks, and conversations I almost canceled. "
            "I worried that the heaviness would be permanent, and that scared me more than I wanted to admit. "
            "Slowly, something shifted: {change}. "
            "The season taught me that {lesson}, and I still keep that close."
        ),
    ],
    "small_moment": [
        (
            "It was an ordinary moment at {place} during {time_of_day}, with {weather} light and {sound} in the distance. "
            "Someone said something small and we laughed in a way that felt unguarded. "
            "At the time it did not feel important, but later it returned to me as proof that peace exists. "
            "That moment matters now because it taught me {lesson}."
        ),
        (
            "I remember the way {smell} hung in the air and how the light made dust look like glitter. "
            "We were just there, no plan, no milestone, just a quiet stretch of time. "
            "Later, when life got busy, that scene came back like a photograph. "
            "It reminded me that {value} can be simple, and that is why I hold onto it."
        ),
    ],
    "advice_echo": [
        (
            "The advice came from {person_role} on an ordinary day at {place}. "
            "They said, \"{advice}\" and it landed in me like a bell. "
            "At the time I resisted, but years later I understood they were naming a kind of wisdom. "
            "It has shaped how I make decisions and how I treat myself, especially when I feel {fear}."
        ),
        (
            "We were standing near {place} when {person_role} offered it, almost casually. "
            "They said, \"{advice}\" and kept moving, as if it were nothing. "
            "I carried it into new seasons, and it taught me that {lesson}."
        ),
    ],
    "childhood_place": [
        (
            "The place was {childhood_place}, and I can still smell {smell} when I think about it. "
            "There was always {sound} somewhere in the background, and the light felt softer in {season}. "
            "That place taught me to love small routines and to notice the ordinary. "
            "It shaped my sense of {value} in ways I did not understand until later."
        ),
        (
            "I can picture {childhood_place} like a map I still carry. "
            "It was where I learned to be curious, to be bored, to invent stories from nothing. "
            "The memory stays because it reminds me that {value} started early, in that quiet corner of life."
        ),
    ],
    "career_turn": [
        (
            "The turning point happened at {place} during {time_of_day}, when I decided {decision}. "
            "I felt {fear} and excitement at the same time, like I was stepping into a room I had not earned yet. "
            "The moment was not dramatic, but it changed my direction. "
            "It taught me that {lesson}, and I still measure choices against that."
        ),
        (
            "For a long time I followed the safe path, until a moment of clarity in {season}. "
            "I chose {decision} and watched my priorities re-order themselves. "
            "It felt risky, but it also felt honest. "
            "That turn taught me {lesson}, which I try to honor at work now."
        ),
    ],
    "friendship_shift": [
        (
            "My friendship with {person_role} changed slowly, not all at once. "
            "We used to talk about everything, then the gaps grew longer and the conversations grew lighter. "
            "It hurt at first, but it also taught me that {lesson}. "
            "I learned to make room for the version of friendship that could still exist."
        ),
        (
            "We were both changing, and the friendship could not stay the same shape. "
            "There was no argument, just a gentle drifting that left me a little sad and a little grateful. "
            "It reminded me that {value} includes letting people evolve without holding on too tightly."
        ),
    ],
    "goodbye": [
        (
            "The goodbye happened at {place} on a {weather} {time_of_day}. "
            "I remember how the air felt and how my voice sounded smaller than I wanted it to. "
            "Saying goodbye to {person_role} taught me that endings can be kind, even when they hurt. "
            "I carry that with me whenever I face change."
        ),
        (
            "I did not expect the goodbye to feel so ordinary. We were just standing there, and suddenly it was over. "
            "What stays with me is not the sadness but the gratitude for the time that came before. "
            "It made me more attentive to the present, which is its own kind of gift."
        ),
    ],
    "unexpected_kindness": [
        (
            "I was having a rough day when {person_role} stepped in and did something small that felt enormous. "
            "It happened at {place}, and the kindness broke through my fog like light. "
            "That moment reminded me that {value} is often simple, and it made me want to pass it on."
        ),
        (
            "The kindness was not a grand gesture. It was a steady, quiet help that showed up right on time. "
            "I remember thinking, \"I am not alone in this,\" and that changed the whole day. "
            "It taught me that {lesson}."
        ),
    ],
    "object_kept": [
        (
            "I still keep {kept_item}. It is small and a little worn, but it holds a whole chapter for me. "
            "Whenever I see it I remember {event} and the way I felt in that season. "
            "It reminds me that {lesson}, and that memory feels like a steady anchor."
        ),
        (
            "The object is {kept_item}, and it lives in a drawer I open more often than I admit. "
            "It brings back the smell of {smell} and the sound of {sound}, like a scene I can step into. "
            "Keeping it is my way of honoring {value}."
        ),
    ],
    "promise_to_self": [
        (
            "I made the promise after {event}, when I realized I could not keep living the same way. "
            "I promised myself {decision}, and the first few days felt clumsy but honest. "
            "Over time the promise became a quiet habit, and it reminded me that {lesson}."
        ),
        (
            "It was a promise to protect my energy and to choose what mattered. "
            "Some days I kept it well, other days I did not, but I kept returning to it. "
            "The promise taught me that {value} is built through repetition, not perfection."
        ),
    ],
    "small_celebration": [
        (
            "The celebration was small--{ritual} at {place} with {food} and {sound} in the background. "
            "It was not flashy, but it felt like a deep exhale after a long stretch of effort. "
            "I remember thinking that joy can be ordinary and still be holy."
        ),
        (
            "We celebrated in the simplest way, but it meant more because we really needed it. "
            "There was laughter, there was {smell}, and there was a sense of relief I did not expect. "
            "It taught me that {value} is worth marking, even in small ways."
        ),
    ],
    "failure_reframe": [
        (
            "I failed at {event}, and for a while it felt like proof that I was not cut out for it. "
            "With time I realized the failure was actually telling me where to grow. "
            "It pushed me toward a version of myself that was more honest and more capable. "
            "That is why I think of it now as a quiet success."
        ),
        (
            "The failure stung at first, especially because I had worked so hard. "
            "But later it taught me {lesson}, and that lesson has done more for me than a quick win would have. "
            "I can see the way it rerouted me in all the best ways."
        ),
    ],
    "belonging": [
        (
            "I felt it at {place}, surrounded by {sound}, when {person_role} pulled me into the moment. "
            "It was not a loud moment, just a quiet recognition that I was part of something. "
            "That feeling taught me that {value} is built in small invitations."
        ),
        (
            "Belonging surprised me. I did not expect to feel it that day, but I did. "
            "I realized that being seen and being useful can happen at the same time. "
            "It left me with a deep sense that {lesson}."
        ),
    ],
    "travel_scene": [
        (
            "The memory is from {city} during {season}, when the air was {weather} and the streets felt new. "
            "I remember walking through {place} and noticing {sound} like it was part of a soundtrack. "
            "It stays with me because it taught me {lesson} in a way no talk ever could."
        ),
        (
            "Travel slows me down, and this trip did exactly that. "
            "There was {smell}, there was {sound}, and there was a quiet sense of being exactly where I was supposed to be. "
            "That day still feels vivid because it showed me {value}."
        ),
    ],
    "quiet_reset": [
        (
            "The reset came during {time_of_day} at {place}, with {weather} light and {object} nearby. "
            "I did nothing dramatic, just sat still and let the noise settle. "
            "It reminded me that {lesson}, and I felt steadier afterward."
        ),
        (
            "It was a quiet evening with {sound} in the background and the smell of {smell}. "
            "I let myself stop chasing productivity and just be human for a while. "
            "That simple pause gave me back a little bit of myself."
        ),
    ],
    "love_in_practice": [
        (
            "I realized it while watching {person_role} do something small for someone else. "
            "There was no speech, just a steady kind of care that kept showing up. "
            "It made me understand that love is often practical, and that changed how I look at it."
        ),
        (
            "Love looked like {activity} and keeping a promise when it was inconvenient. "
            "It was not dramatic, just reliable. "
            "That moment rewired my idea of what love actually is."
        ),
    ],
    "decision_change": [
        (
            "The decision came after a long stretch of pretending everything was fine. "
            "I chose {decision} and felt both relief and fear at once. "
            "The weeks after were messy, but they were honest, and that mattered."
        ),
        (
            "I decided to change something important in {season}, when I finally admitted I was unhappy. "
            "The shift was not quick, but it was real. "
            "I learned that {lesson}, and it keeps me from drifting now."
        ),
    ],
}

FORMATS = ["qa", "note"]
FORMAT_WEIGHTS = [0.85, 0.15]

RELATIONS = [
    "my mom",
    "my dad",
    "my sister",
    "my brother",
    "my partner",
    "my best friend",
    "my mentor",
    "my cousin",
    "my neighbor",
    "my coworker",
]

PLACES = [
    "the kitchen",
    "the porch",
    "the backyard",
    "the beach",
    "the mountains",
    "a hospital hallway",
    "a crowded subway",
    "a quiet cafe",
    "the high school gym",
    "a college dorm room",
    "the living room floor",
    "a small bookstore",
    "a winding trail",
    "a city street at night",
    "the airport gate",
]

CHILDHOOD_PLACES = [
    "the neighborhood cul-de-sac",
    "the old playground",
    "my grandparents' living room",
    "the back steps",
    "the corner store",
    "the creek behind the house",
    "the attic",
    "the summer cabin",
]

CITIES = ["Chicago", "Seattle", "Austin", "Boston", "San Diego", "Denver", "Nashville", "New York"]

TIME_OF_DAY = [
    "early morning",
    "late afternoon",
    "just before sunset",
    "after dinner",
    "near midnight",
    "right before sunrise",
]

SEASONS = ["winter", "spring", "summer", "fall"]
WEATHER = ["rainy", "windy", "foggy", "sunny", "snowy", "humid"]

RITUALS = ["Sunday dinner", "birthday breakfast", "holiday baking", "evening walks", "Saturday market"]
FOODS = ["warm soup", "fresh bread", "stir-fry", "pancakes", "a simple salad", "coffee"]

OBJECTS = ["a mug", "a blanket", "a notebook", "a candle", "a coffee cup"]
SOUNDS = ["dishes clinking", "rain on the roof", "traffic in the distance", "laughter from the hallway", "the kettle whistling"]
SMELLS = ["fresh bread", "rain-soaked pavement", "coffee", "pine trees", "laundry detergent"]

EVENTS = [
    "a graduation",
    "a wedding",
    "a new job",
    "a move",
    "a breakup",
    "a promotion",
    "a diagnosis",
    "a loss",
    "a first apartment",
]

MILESTONES = [
    "finished my degree",
    "moved to a new city",
    "bought my first car",
    "started a new job",
    "ended a long chapter",
]

ACTIVITIES = [
    "driving home",
    "folding laundry",
    "packing boxes",
    "waiting in line",
    "walking the dog",
    "setting the table",
    "cleaning out a drawer",
]

KEPT_ITEMS = [
    "a handwritten note",
    "an old photo",
    "a small ticket stub",
    "a keychain",
    "a battered suitcase",
    "a sweater",
]

LESSONS = [
    "courage does not feel loud",
    "love shows up in small acts",
    "honesty is a kind of relief",
    "consistency is a quiet kind of strength",
    "asking for help is not weakness",
    "you do not have to earn rest",
]

VALUES = ["belonging", "patience", "integrity", "curiosity", "steadiness", "grace"]
FEARS = ["being found out", "letting someone down", "starting over", "being alone", "failing in public"]

ADVICE = [
    "Do not confuse exhaustion with importance.",
    "Let the simple thing be enough.",
    "You can be kind and still be clear.",
    "Make the decision you can live with on your hardest day.",
]

DECISIONS = [
    "to speak up",
    "to leave a role that no longer fit",
    "to ask for help",
    "to apologize",
    "to start over",
    "to take the risk",
]

CHANGES = [
    "everything slowed down",
    "I started noticing the small wins",
    "the pressure lifted a little",
    "I stopped pretending",
    "my priorities shifted",
]

EMOTIONS = [
    "joy",
    "calm",
    "gratitude",
    "stress",
    "anticipation",
    "contentment",
    "frustration",
    "hope",
    "pride",
    "tenderness",
]

EMOTION_BY_TOPIC = {
    "hard_season": ["stress", "frustration", "hope"],
    "goodbye": ["tenderness", "gratitude"],
    "family_tradition": ["gratitude", "joy"],
    "self_surprise": ["pride", "anticipation"],
}

SENTIMENT_BY_TOPIC = {
    "hard_season": "neutral",
    "goodbye": "neutral",
    "failure_reframe": "neutral",
}


class SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _strip_json_fences(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def _parse_json_payload(text: str) -> Optional[Dict[str, object]]:
    if not text:
        return None
    cleaned = _strip_json_fences(text)
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None


def _listify(value: object) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value).strip()]


def _extend_unique(items: List[str], additions: List[str], limit: int) -> List[str]:
    if not additions:
        return items
    existing = {item.lower() for item in items}
    for item in additions:
        cleaned = str(item).strip()
        if not cleaned:
            continue
        if cleaned.lower() in existing:
            continue
        items.append(cleaned)
        existing.add(cleaned.lower())
    if len(items) > limit:
        items = items[-limit:]
    return items


def _normalize_memory_type(value: object) -> MemoryType:
    raw = str(value or "").lower()
    for item in MemoryType:
        if item.value == raw:
            return item
    return MemoryType.EVENT


def _select_month_context(story_bible: Dict[str, object], date: datetime) -> Dict[str, object]:
    month_label = date.strftime("%B")
    outline = story_bible.get("year_outline") or []
    for item in outline:
        if not isinstance(item, dict):
            continue
        label = str(item.get("month", "")).strip()
        if not label:
            continue
        if label.lower().startswith(month_label.lower()):
            return item
    return {}


def _generate_story_bible(days: int) -> Optional[Dict[str, object]]:
    system_msg = (
        "You are generating a coherent year-long journaling dataset for a single person. "
        "Return strict JSON only."
    )
    user_msg = (
        "Create a story bible for one realistic person whose journal entries will span about "
        f"{days} days. The bible must keep stories consistent and interconnected.\n\n"
        "Return JSON with keys:\n"
        "- persona: {name, age, pronouns, hometown, current_city, occupation, employer, "
        "relationship_status, household, pets, voice, values, health_notes}\n"
        "- recurring_people: 8-12 items [{name, relation, notes, location}]\n"
        "- recurring_places: {home_base, work_spot, favorite_spots, cities, countries}\n"
        "- recurring_foods: [foods]\n"
        "- hobbies: [hobbies]\n"
        "- recurring_themes: [short phrases]\n"
        "- canonical_facts: [short statements that must stay true]\n"
        "- year_outline: 12 items with {month, arc, key_events, ongoing_threads, travel}\n"
        "Include at least 4 cities and 2 countries. Keep details grounded and avoid dramatic events. "
        "Use everyday life, work, relationships, and personal growth. Output JSON only."
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.6,
            max_tokens=900,
        )
    except Exception:
        return None
    content = resp.choices[0].message.content if resp.choices else ""
    payload = _parse_json_payload(content)
    if isinstance(payload, dict):
        return payload
    return None


def _generate_openai_entry(
    date: datetime,
    story_bible: Dict[str, object],
    prompt_seed: Optional[str],
    memory_type: Optional[MemoryType],
    style: str,
    recent_context: List[str],
    continuity_notes: List[str],
) -> Optional[Dict[str, object]]:
    month_context = _select_month_context(story_bible, date)
    persona = story_bible.get("persona", {})
    people = story_bible.get("recurring_people", [])
    places = story_bible.get("recurring_places", {})
    themes = story_bible.get("recurring_themes", [])
    foods = story_bible.get("recurring_foods", [])
    hobbies = story_bible.get("hobbies", [])
    facts = story_bible.get("canonical_facts", [])

    people_line = ", ".join(
        [f"{p.get('name')} ({p.get('relation')})" for p in people if isinstance(p, dict) and p.get("name")]
    )
    places_line = ""
    if isinstance(places, dict):
        parts = []
        for key in ("home_base", "work_spot"):
            val = places.get(key)
            if val:
                parts.append(f"{key}: {val}")
        for key in ("favorite_spots", "cities", "countries"):
            items = places.get(key) or []
            if items:
                parts.append(f"{key}: {', '.join([str(item) for item in items])}")
        places_line = " | ".join(parts)
    else:
        places_line = ", ".join([str(place) for place in places if str(place).strip()])
    recent_line = "\n".join([f"- {item}" for item in recent_context if item]) or "None"
    continuity_line = "\n".join([f"- {item}" for item in continuity_notes if item]) or "None"
    prompt_seed_line = f"Prompt seed: {prompt_seed}" if prompt_seed else "Prompt seed: (generate one)"
    memory_line = f"Memory type: {memory_type.value}" if memory_type else "Memory type: choose best fit"

    system_msg = (
        "You write grounded, coherent journal prompt/answer pairs for the same person across a year. "
        "Stay consistent with persona details and timeline. Avoid stock phrases, avoid melodrama, "
        "and avoid repeating imagery from recent entries. Output strict JSON only."
    )
    user_msg = (
        f"Date: {date.strftime('%Y-%m-%d')}\n"
        f"{prompt_seed_line}\n"
        f"{memory_line}\n"
        f"Style: {style} (qa = Q/A; note = short prompt + freeform answer)\n\n"
        f"Persona: {persona}\n"
        f"Recurring people: {people_line}\n"
        f"Recurring places: {places_line}\n"
        f"Recurring foods: {foods}\n"
        f"Hobbies: {hobbies}\n"
        f"Recurring themes: {themes}\n"
        f"Canonical facts (must remain true): {facts}\n"
        f"Month context: {month_context}\n"
        f"Continuity notes (keep consistent):\n{continuity_line}\n"
        f"Recent entries (avoid repeating):\n{recent_line}\n\n"
        "Write one prompt and answer that could plausibly be written on this date. "
        "The prompt should be one sentence and end with a question mark. "
        "The answer should be 90-160 words, first-person, specific, and tied to the month context. "
        "Include at least one named person, one place (city/country or local), and one concrete detail "
        "(food, pet, object, or sensory detail). If pets or recurring foods exist, mention one. "
        "Use consistent names and places; introduce new names "
        "or places only if the month context suggests a new connection. "
        "Do not include labels like 'Q:' or 'A:' in the fields.\n\n"
        "Return JSON with keys: prompt, answer, summary, memory_type, topics, people, places, emotion, "
        "sentiment_label, sentiment_score, continuity_updates. topics/people/places/continuity_updates must be lists."
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.65,
            max_tokens=500,
        )
    except Exception:
        return None
    content = resp.choices[0].message.content if resp.choices else ""
    payload = _parse_json_payload(content)
    if not isinstance(payload, dict):
        return None
    return payload

def wipe_entries() -> int:
    """Delete all Entry rows and return the count removed."""
    with get_session() as session:
        existing = session.exec(select(Entry)).all()
        count = len(existing)
        session.exec(delete(Entry))
        session.commit()
        return count


def _build_answer(topic: str, context: Dict[str, str]) -> str:
    template = random.choice(ANSWER_TEMPLATES[topic])
    return template.format_map(SafeDict(context)).strip()


def _build_text(style: str, prompt: str, answer: str) -> str:
    if style == "note":
        return f"Prompt: {prompt}\n\n{answer}\n\nReflection: {random.choice(LESSONS)}."
    return f"Q: {prompt}\nA: {answer}"


def _pick_emotion(topic: str) -> str:
    if topic in EMOTION_BY_TOPIC:
        return random.choice(EMOTION_BY_TOPIC[topic])
    return random.choice(EMOTIONS)


def _sentiment_for_topic(topic: str) -> tuple[str, float]:
    label = SENTIMENT_BY_TOPIC.get(topic, "positive")
    if label == "positive":
        score = random.uniform(0.6, 0.95)
    elif label == "negative":
        score = random.uniform(0.1, 0.4)
    else:
        score = random.uniform(0.4, 0.7)
    return label, round(score, 2)


def _summarize(answer: str) -> str:
    sentence = answer.split(".", 1)[0].strip()
    if not sentence:
        return answer[:120]
    return sentence + "."


def _build_context() -> Dict[str, str]:
    person_role = random.choice(RELATIONS)
    second_person_role = random.choice([role for role in RELATIONS if role != person_role])
    return {
        "person_role": person_role,
        "second_person_role": second_person_role,
        "place": random.choice(PLACES),
        "childhood_place": random.choice(CHILDHOOD_PLACES),
        "city": random.choice(CITIES),
        "time_of_day": random.choice(TIME_OF_DAY),
        "season": random.choice(SEASONS),
        "weather": random.choice(WEATHER),
        "ritual": random.choice(RITUALS),
        "food": random.choice(FOODS),
        "object": random.choice(OBJECTS),
        "sound": random.choice(SOUNDS),
        "smell": random.choice(SMELLS),
        "event": random.choice(EVENTS),
        "milestone": random.choice(MILESTONES),
        "activity": random.choice(ACTIVITIES),
        "kept_item": random.choice(KEPT_ITEMS),
        "fear": random.choice(FEARS),
        "lesson": random.choice(LESSONS),
        "value": random.choice(VALUES),
        "advice": random.choice(ADVICE),
        "decision": random.choice(DECISIONS),
        "change": random.choice(CHANGES),
    }


def _build_dates(count: int, days: int) -> List[datetime]:
    now = datetime.utcnow()
    dates = []
    for _ in range(count):
        dates.append(
            now
            - timedelta(
                days=random.randint(0, days),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
        )
    dates.sort()
    return dates


def _build_entry_from_openai(
    payload: Dict[str, object],
    style: str,
    created_at: datetime,
    default_memory_type: Optional[MemoryType] = None,
) -> Entry:
    prompt = str(payload.get("prompt") or "").strip()
    if prompt and not prompt.endswith("?"):
        prompt = prompt.rstrip(".") + "?"
    answer = str(payload.get("answer") or "").strip()
    summary = str(payload.get("summary") or "").strip() or _summarize(answer)
    topics = _listify(payload.get("topics")) or ["journal"]
    people = _listify(payload.get("people"))
    places = _listify(payload.get("places"))
    emotion = str(payload.get("emotion") or "neutral").strip()
    sentiment_label = str(payload.get("sentiment_label") or "neutral").strip().lower()
    if sentiment_label not in {"positive", "neutral", "negative"}:
        sentiment_label = "neutral"
    try:
        sentiment_score = float(payload.get("sentiment_score", 0.6))
    except (TypeError, ValueError):
        sentiment_score = 0.6
    sentiment_score = max(0.0, min(1.0, sentiment_score))
    memory_type = _normalize_memory_type(payload.get("memory_type") or default_memory_type)
    tags = list(dict.fromkeys(topics + [style, "prompt-qa", "seeded", "openai"]))

    prompt_fallback = prompt or "What moment from today stands out most?"
    text = _build_text(style, prompt_fallback, answer)
    return Entry(
        user_id="default-user",
        source_type="text",
        original_text=text,
        content=text,
        summary=summary,
        topics=", ".join(tags),
        emotions=emotion,
        emotion_scores=json.dumps({emotion: round(random.uniform(0.6, 0.95), 2)}),
        people=", ".join(people) if people else None,
        places=", ".join(places) if places else None,
        tags=tags,
        word_count=len(text.split()),
        memory_type=memory_type,
        title=prompt_fallback,
        source=SourceType.TYPED,
        confidence_score=0.9,
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
        processing_status="complete",
        updated_at=created_at,
        created_at=created_at,
    )


def _attach_embedding(entry: Entry) -> None:
    text = entry.content or entry.original_text or ""
    vec = embed_text(text)
    entry.embedding = serialize_embedding(vec)


def seed_random_qa(count: int, days: int, use_openai: bool = False) -> int:
    rows: List[Entry] = []
    if not use_openai:
        now = datetime.utcnow()
        for _ in range(count):
            prompt_meta = random.choice(PROMPTS)
            topic = str(prompt_meta["topic"])
            prompt = str(prompt_meta["prompt"])
            context = _build_context()
            answer = _build_answer(topic, context)
            style = random.choices(FORMATS, weights=FORMAT_WEIGHTS, k=1)[0]
            text = _build_text(style, prompt, answer)
            created_at = now - timedelta(
                days=random.randint(0, days),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            summary = _summarize(answer)
            sentiment_label, sentiment_score = _sentiment_for_topic(topic)
            emotion = _pick_emotion(topic)
            tags = [topic, style, "storyworth", "prompt-qa", "longform"]
            people = [context["person_role"], context["second_person_role"]]
            if random.random() < 0.4:
                people = [context["person_role"]]
            places = [context["place"]] if random.random() < 0.6 else []

            rows.append(
                Entry(
                    user_id="default-user",
                    source_type="text",
                    original_text=text,
                    content=text,
                    summary=summary,
                    topics=", ".join(tags),
                    emotions=emotion,
                    emotion_scores=json.dumps({emotion: round(random.uniform(0.6, 0.95), 2)}),
                    people=", ".join(people) if people else None,
                    places=", ".join(places) if places else None,
                    tags=tags,
                    word_count=len(text.split()),
                    memory_type=prompt_meta["memory_type"],
                    title=prompt,
                    source=SourceType.TYPED,
                    confidence_score=0.9,
                    sentiment_label=sentiment_label,
                    sentiment_score=sentiment_score,
                    processing_status="complete",
                    updated_at=created_at,
                    created_at=created_at,
                )
            )
    else:
        story_bible = _generate_story_bible(days)
        if not story_bible:
            print(
                "OpenAI story bible generation failed; falling back to template seeding.",
                file=sys.stderr,
            )
            return seed_random_qa(count, days, use_openai=False)
        recent_context: List[str] = []
        continuity_notes: List[str] = []
        dates = _build_dates(count, days)
        openai_failures = 0
        for created_at in dates:
            prompt_meta = random.choice(PROMPTS)
            style = random.choices(FORMATS, weights=FORMAT_WEIGHTS, k=1)[0]
            prompt_seed = str(prompt_meta["prompt"]) if random.random() < 0.7 else None
            payload = _generate_openai_entry(
                created_at,
                story_bible,
                prompt_seed=prompt_seed,
                memory_type=prompt_meta["memory_type"],
                style=style,
                recent_context=recent_context[-RECENT_CONTEXT_LIMIT:],
                continuity_notes=continuity_notes[-CONTINUITY_LIMIT:],
            )
            if not payload:
                openai_failures += 1
                topic = str(prompt_meta["topic"])
                context = _build_context()
                answer = _build_answer(topic, context)
                summary = _summarize(answer)
                sentiment_label, sentiment_score = _sentiment_for_topic(topic)
                emotion = _pick_emotion(topic)
                tags = [topic, style, "storyworth", "prompt-qa", "longform"]
                text = _build_text(style, str(prompt_meta["prompt"]), answer)
                fallback_entry = Entry(
                    user_id="default-user",
                    source_type="text",
                    original_text=text,
                    content=text,
                    summary=summary,
                    topics=", ".join(tags),
                    emotions=emotion,
                    emotion_scores=json.dumps({emotion: round(random.uniform(0.6, 0.95), 2)}),
                    people=None,
                    places=None,
                    tags=tags,
                    word_count=len(text.split()),
                    memory_type=prompt_meta["memory_type"],
                    title=str(prompt_meta["prompt"]),
                    source=SourceType.TYPED,
                    confidence_score=0.9,
                    sentiment_label=sentiment_label,
                    sentiment_score=sentiment_score,
                    processing_status="complete",
                    updated_at=created_at,
                    created_at=created_at,
                )
                _attach_embedding(fallback_entry)
                rows.append(fallback_entry)
                continue

            entry = _build_entry_from_openai(payload, style, created_at, prompt_meta["memory_type"])
            _attach_embedding(entry)
            rows.append(entry)
            summary = str(payload.get("summary") or "").strip()
            if summary:
                recent_context.append(summary)
            continuity_updates = _listify(payload.get("continuity_updates"))
            continuity_notes = _extend_unique(continuity_notes, continuity_updates, CONTINUITY_LIMIT)
        if openai_failures:
            print(
                f"OpenAI entry generation failed {openai_failures} times; used template fallback.",
                file=sys.stderr,
            )

    with get_session() as session:
        session.add_all(rows)
        session.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed story-forward prompt/answer entries for local testing."
    )
    parser.add_argument("--wipe", action="store_true", help="Delete existing entries first.")
    parser.add_argument("--count", type=int, default=500, help="Number of entries to seed.")
    parser.add_argument("--days", type=int, default=365, help="Spread entries across N days.")
    parser.add_argument(
        "--openai",
        action="store_true",
        help="Use OpenAI to generate a coherent single-person dataset.",
    )
    args = parser.parse_args()

    if args.openai and not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; --openai requires it.", file=sys.stderr)
        sys.exit(1)

    init_db()
    migrate_db()

    if args.wipe:
        deleted = wipe_entries()
        print(f"Wiped {deleted} existing entries.")

    inserted = seed_random_qa(args.count, args.days, use_openai=args.openai)
    print(f"Inserted {inserted} prompt/answer entries.")


if __name__ == "__main__":
    main()
