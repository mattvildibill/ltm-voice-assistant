import base64
import io
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from sqlmodel import select

from app.db.database import get_session
from app.models.entry import Entry
from app.services.openai_service import client


CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720
DEFAULT_DURATION = 15
WORDS_PER_SECOND = 2.4
DEFAULT_VOICE = "alloy"
IMAGE_MODEL = "gpt-image-1"

STYLE_PROMPT = (
    "Flat pastel cartoon illustration, soft gradients, minimal shading, clean shapes, "
    "2D, wide 16:9 composition, no text, no captions, no logos, no watermarks."
)
CHARACTER_PROMPT = (
    "Recurring character in every scene: friendly androgynous adult, short wavy hair, "
    "warm teal sweater, expressive eyes, calm smile. Keep character design consistent."
)


def _wrap_text(draw, text: str, font, max_width: int) -> List[str]:
    words = (text or "").split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _text_width(draw, text: str, font) -> int:
    try:
        return int(draw.textlength(text, font=font))
    except Exception:
        bbox = draw.textbbox((0, 0), text, font=font)
        return int(bbox[2] - bbox[0])


def _truncate_words(text: str, limit: int) -> str:
    words = (text or "").split()
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]).strip()


def _json_from_text(raw: str) -> Optional[Dict]:
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


def _load_font(size: int, bold: bool = False):
    try:
        from PIL import ImageFont
    except Exception as exc:  # pragma: no cover - import failure handled by caller
        raise RuntimeError("Pillow is required to render video frames.") from exc

    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _render_slide(slide: Dict, output_path: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError("Pillow is required to render video frames.") from exc

    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), color=(8, 12, 24))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(CANVAS_HEIGHT):
        ratio = y / float(CANVAS_HEIGHT)
        r = int(10 + ratio * 24)
        g = int(18 + ratio * 30)
        b = int(36 + ratio * 60)
        draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(r, g, b))

    draw.rectangle([(0, 0), (18, CANVAS_HEIGHT)], fill=(108, 240, 194))

    title_font = _load_font(60)
    body_font = _load_font(34)
    muted_font = _load_font(24)

    margin_x = 80
    y = 80

    title = slide.get("title", "").strip()
    if title:
        draw.text((margin_x, y), title, font=title_font, fill=(234, 240, 255))
        y += 86

    subtitle = slide.get("subtitle", "").strip()
    if subtitle:
        draw.text((margin_x, y), subtitle, font=muted_font, fill=(159, 178, 215))
        y += 46

    lines = slide.get("lines", [])
    for line in lines:
        for wrapped in _wrap_text(draw, line, body_font, CANVAS_WIDTH - margin_x * 2):
            draw.text((margin_x, y), wrapped, font=body_font, fill=(226, 233, 255))
            y += 48
        y += 6

    img.save(output_path)


def _render_fallback_scene(output_path: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError("Pillow is required to render fallback scenes.") from exc

    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), color=(8, 12, 24))
    draw = ImageDraw.Draw(img)

    for y in range(CANVAS_HEIGHT):
        ratio = y / float(CANVAS_HEIGHT)
        r = int(12 + ratio * 26)
        g = int(18 + ratio * 24)
        b = int(42 + ratio * 46)
        draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(r, g, b))

    draw.rectangle([(0, 0), (18, CANVAS_HEIGHT)], fill=(108, 240, 194))
    img.save(output_path)


def _resize_to_canvas(img) -> "Image":
    width, height = img.size
    target_ratio = CANVAS_WIDTH / CANVAS_HEIGHT
    current_ratio = width / height if height else target_ratio

    if current_ratio > target_ratio:
        new_width = int(height * target_ratio)
        left = (width - new_width) // 2
        img = img.crop((left, 0, left + new_width, height))
    elif current_ratio < target_ratio:
        new_height = int(width / target_ratio)
        top = (height - new_height) // 2
        img = img.crop((0, top, width, top + new_height))

    return img.resize((CANVAS_WIDTH, CANVAS_HEIGHT))


def _generate_scene_image(prompt: str, output_path: Path) -> None:
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError("Pillow is required to render video frames.") from exc

    response = None
    try:
        response = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size="1792x1024",
            response_format="b64_json",
        )
    except Exception:
        response = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size="1792x1024",
        )

    data = None
    if response and getattr(response, "data", None):
        item = response.data[0]
        b64 = None
        url = None
        if isinstance(item, dict):
            b64 = item.get("b64_json")
            url = item.get("url")
        else:
            b64 = getattr(item, "b64_json", None)
            url = getattr(item, "url", None)

        if b64:
            data = base64.b64decode(b64)
        elif url:
            import urllib.request
            with urllib.request.urlopen(url) as resp:
                data = resp.read()

    if not data:
        raise RuntimeError("Image generation returned no data.")

    img = Image.open(io.BytesIO(data))
    img = _resize_to_canvas(img)
    img.save(output_path)


def _ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to render the weekly video.")


def _generate_audio(script: str, output_path: Path, voice: str) -> None:
    response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=script,
    )

    try:
        response.write_to_file(str(output_path))
        return
    except Exception:
        pass

    data = None
    for attr in ("content", "read"):
        if hasattr(response, attr):
            data = getattr(response, attr)
            break

    if callable(data):
        payload = data()
    else:
        payload = data

    if not payload:
        raise RuntimeError("Unable to write TTS audio to file.")

    output_path.write_bytes(payload)


def _render_video_from_frames(
    frame_paths: List[Path],
    audio_path: Path,
    output_path: Path,
    duration: int,
) -> None:
    _ensure_ffmpeg()

    frames_file = output_path.parent / "frames.txt"
    seconds_per = max(duration / max(len(frame_paths), 1), 1.0)

    lines = []
    for frame in frame_paths:
        frame_path = frame.resolve().as_posix()
        lines.append(f"file '{frame_path}'")
        lines.append(f"duration {seconds_per:.2f}")
    lines.append(f"file '{frame_paths[-1].resolve().as_posix()}'")
    frames_file.write_text("\n".join(lines))

    silent_video = output_path.parent / "video_silent.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(frames_file),
            "-fps_mode",
            "vfr",
            "-pix_fmt",
            "yuv420p",
            str(silent_video),
        ],
        check=True,
        capture_output=True,
    )

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(silent_video),
            "-i",
            str(audio_path),
            "-filter_complex",
            f"[1:a]atrim=duration={duration},apad=pad_dur={duration}[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def _build_weekly_storyboard(user_id: str, duration: int) -> Dict:
    cutoff = datetime.utcnow() - timedelta(days=7)
    with get_session() as session:
        entries = session.exec(
            select(Entry)
            .where(Entry.user_id == user_id, Entry.created_at >= cutoff)
            .order_by(Entry.created_at.desc())
        ).all()

    if not entries:
        raise ValueError("No entries found in the last 7 days.")

    total_entries = len(entries)
    total_words = sum(entry.word_count or len((entry.original_text or "").split()) for entry in entries)

    topic_counts: Dict[str, int] = {}
    emotion_counts: Dict[str, int] = {}
    people_counts: Dict[str, int] = {}
    places_counts: Dict[str, int] = {}
    sentiment_scores: List[float] = []

    def bump(counter: Dict[str, int], values: List[str]):
        for value in values:
            if not value:
                continue
            counter[value] = counter.get(value, 0) + 1

    def split_values(value: Optional[str]) -> List[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    for entry in entries:
        bump(topic_counts, split_values(entry.topics))
        bump(emotion_counts, split_values(entry.emotions))
        bump(people_counts, split_values(entry.people))
        bump(places_counts, split_values(entry.places))
        if entry.sentiment_score is not None:
            sentiment_scores.append(entry.sentiment_score)

    def top_keys(counter: Dict[str, int], limit: int = 3) -> List[str]:
        return [k for k, _ in sorted(counter.items(), key=lambda item: item[1], reverse=True)[:limit]]

    highlight_count = 2 if duration <= 15 else 3
    highlights = []
    for entry in entries[:highlight_count]:
        text = (entry.summary or entry.original_text or "").strip().replace("\n", " ")
        if len(text) > 140:
            text = text[:137] + "..."
        if text:
            highlights.append(text)

    top_emotions = top_keys(emotion_counts)
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else None

    stats = {
        "total_entries": total_entries,
        "total_words": total_words,
        "top_topics": top_keys(topic_counts),
        "top_emotions": top_emotions,
        "top_people": top_keys(people_counts),
        "top_places": top_keys(places_counts),
        "average_sentiment": avg_sentiment,
        "highlights": highlights,
    }

    target_words = max(int(duration * WORDS_PER_SECOND), 20)
    min_words = max(target_words - 6, 16)
    max_words = max(target_words + 6, min_words + 4)

    prompt = (
        f"Create a {duration} second weekly recap script for a user's personal memories. "
        "Return JSON with keys: title, summary, highlights, themes, closing, script. "
        f"Script should be {min_words}-{max_words} words. Highlights and themes should be short phrases."
        f"\nStats: {stats}"
    )

    script_data = None
    try:
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You write warm, concise weekly recap videos."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
            )
        except Exception:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You write warm, concise weekly recap videos."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
            )
        content = resp.choices[0].message.content if resp.choices else ""
        if content:
            script_data = json.loads(content)
    except Exception:
        script_data = None

    if not isinstance(script_data, dict):
        script_data = _json_from_text(str(script_data)) or {}

    title = script_data.get("title") or "Your Week in Review"
    summary = script_data.get("summary") or (
        f"You captured {total_entries} memories this week with {total_words} words."
    )
    themes = script_data.get("themes") or stats["top_topics"] or ["Connections", "Growth", "Moments"]
    closing = script_data.get("closing") or "What do you want to carry forward into next week?"
    script = script_data.get("script") or (
        f"This week you recorded {total_entries} memories. "
        f"Highlights included {', '.join(highlights) if highlights else 'several meaningful moments'}. "
        f"Recurring themes were {', '.join(themes)}. "
        f"Your mood leaned {top_emotions[0] if top_emotions else 'steady'}. "
        f"{closing}"
    )

    script = _truncate_words(script, max_words)

    date_range = f"{(cutoff.date()).isoformat()} to {datetime.utcnow().date().isoformat()}"

    slides = [
        {"title": title, "subtitle": date_range, "lines": [f"{total_entries} entries captured"]},
        {"title": "Summary", "lines": [summary]},
        {"title": "Highlights", "lines": [f"- {item}" for item in highlights] or ["- Moments worth remembering"]},
        {
            "title": "Themes",
            "lines": [
                f"Topics: {', '.join(stats['top_topics']) or 'No dominant topics'}",
                f"People: {', '.join(stats['top_people']) or 'No people tagged'}",
                f"Places: {', '.join(stats['top_places']) or 'No places tagged'}",
            ],
        },
        {
            "title": "Mood",
            "lines": [
                f"Top emotions: {', '.join(top_emotions) or 'Neutral'}",
                f"Average sentiment: {round(avg_sentiment, 2) if avg_sentiment is not None else 'n/a'}",
            ],
        },
        {"title": "Looking Ahead", "lines": [closing]},
    ]

    if duration <= 15:
        slides = [slides[0], slides[1], slides[2], slides[-1]]

    scene_prompts = _build_scene_prompts(
        stats,
        highlights,
        themes,
        closing,
        date_range,
        max_scenes=len(slides),
    )

    return {
        "slides": slides,
        "script": script,
        "title": title,
        "stats": stats,
        "scene_prompts": scene_prompts,
    }


def _build_scene_prompts(
    stats: Dict,
    highlights: List[str],
    themes: List[str],
    closing: str,
    date_range: str,
    max_scenes: int,
) -> List[str]:
    topics = stats.get("top_topics") or []
    emotions = stats.get("top_emotions") or []
    people = stats.get("top_people") or []
    places = stats.get("top_places") or []

    topic_text = ", ".join(topics) if topics else "everyday life"
    emotion_text = ", ".join(emotions) if emotions else "steady calm"

    highlight_hint = "moments from the week"
    if highlights:
        highlight_hint = _truncate_words(" ".join(highlights), 10)

    people_hint = "close connections" if people else "friends and family"
    places_hint = "familiar spaces" if places else "cozy places"

    closing_hint = _truncate_words(closing, 12) if closing else "looking ahead with curiosity"

    scenes = [
        f"{STYLE_PROMPT} {CHARACTER_PROMPT} Scene: The character reviews a weekly calendar on a desk, "
        f"soft icons floating around (hearts, stars, speech bubbles). Date range: {date_range}.",
        f"{STYLE_PROMPT} {CHARACTER_PROMPT} Scene: The character reflects in a cozy room, "
        f"surrounded by abstract icons representing {topic_text}.",
        f"{STYLE_PROMPT} {CHARACTER_PROMPT} Scene: A collage of small vignettes around the character "
        f"hinting at {highlight_hint}, friendly and uplifting.",
        f"{STYLE_PROMPT} {CHARACTER_PROMPT} Scene: The character connects threads between icons for "
        f"{people_hint} and {places_hint}, with gentle pastel lines.",
        f"{STYLE_PROMPT} {CHARACTER_PROMPT} Scene: The character sits beneath a sky gradient "
        f"representing mood, with symbols for {emotion_text}.",
        f"{STYLE_PROMPT} {CHARACTER_PROMPT} Scene: The character looks toward a sunrise path, "
        f"hopeful and calm, embodying the closing thought: {closing_hint}.",
    ]

    return scenes[:max_scenes]


def generate_weekly_video(
    user_id: str,
    output_dir: Path,
    duration: int = DEFAULT_DURATION,
    voice: str = DEFAULT_VOICE,
) -> Dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = _build_weekly_storyboard(user_id, duration)
    slides = plan["slides"]
    script = plan["script"]
    scene_prompts = plan.get("scene_prompts") or []

    frame_paths = []
    for idx, slide in enumerate(slides, start=1):
        frame_path = output_dir / f"frame_{idx:02d}.png"
        prompt = scene_prompts[idx - 1] if idx - 1 < len(scene_prompts) else None
        try:
            if prompt:
                _generate_scene_image(prompt, frame_path)
            else:
                _render_fallback_scene(frame_path)
        except Exception:
            _render_fallback_scene(frame_path)
        frame_paths.append(frame_path)

    audio_path = output_dir / "narration.mp3"
    _generate_audio(script, audio_path, voice)

    output_path = output_dir / "weekly_video.mp4"
    _render_video_from_frames(frame_paths, audio_path, output_path, duration=duration)

    return {
        "video_path": str(output_path),
        "script": script,
        "slides": slides,
        "scene_prompts": scene_prompts,
        "title": plan.get("title"),
        "duration": duration,
    }
