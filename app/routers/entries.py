from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.core.auth import get_current_user_id
from app.db.database import get_session
from app.models.entry import Entry, MemoryType
from app.services import entry_service

router = APIRouter()


class EntryUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    original_text: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    memory_type: Optional[MemoryType] = None
    people: Optional[List[str]] = None
    places: Optional[List[str]] = None


class EntryFlagRequest(BaseModel):
    flagged: bool = True
    reason: Optional[str] = None


def _clean_list(values: Optional[List[str]]) -> Optional[List[str]]:
    if values is None:
        return None
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    return cleaned


def _join_list(values: Optional[List[str]]) -> Optional[str]:
    cleaned = _clean_list(values)
    if not cleaned:
        return None
    return ", ".join(cleaned)


def _split(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]

def _get_entry(session, entry_id: str, user_id: str) -> Optional[Entry]:
    return session.exec(
        select(Entry).where(Entry.id == entry_id, Entry.user_id == user_id)
    ).first()


def _get_entry(session, entry_id: str, user_id: str) -> Optional[Entry]:
    return session.exec(
        select(Entry).where(Entry.id == entry_id, Entry.user_id == user_id)
    ).first()


@router.post("/entries")
async def add_entry(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    source: Optional[str] = Form(None),
    confidence_score: Optional[float] = Form(None),
    user_id: str = Depends(get_current_user_id),
    background_tasks: BackgroundTasks = None,
):
    """
    Accepts text OR audio.
    """
    try:
        return await entry_service.process_entry(
            text=text,
            file=file,
            source=source,
            confidence_score=confidence_score,
            user_id=user_id,
            background_tasks=background_tasks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/entries/{entry_id}")
def update_entry(
    entry_id: str,
    payload: EntryUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Edit key entry fields (title, content, tags, memory_type, people, places, summary).
    """
    updates = payload.dict(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update.")

    with get_session() as session:
        entry = _get_entry(session, entry_id, user_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found.")

        now = datetime.utcnow()
        text_updated = False

        if "title" in updates:
            title = (updates.get("title") or "").strip()
            entry.title = title or None

        if "summary" in updates:
            summary = (updates.get("summary") or "").strip()
            entry.summary = summary or None

        if "content" in updates or "original_text" in updates:
            content_val = updates.get("content")
            original_val = updates.get("original_text")

            if content_val is not None:
                if content_val != entry.content:
                    text_updated = True
                entry.content = content_val
                if original_val is None:
                    entry.original_text = content_val
            if original_val is not None:
                if original_val != entry.original_text:
                    text_updated = True
                entry.original_text = original_val
                if content_val is None:
                    entry.content = original_val

        if "tags" in updates:
            entry.tags = _clean_list(updates.get("tags")) or None

        if "memory_type" in updates:
            entry.memory_type = updates.get("memory_type") or entry.memory_type

        if "people" in updates:
            entry.people = _join_list(updates.get("people"))

        if "places" in updates:
            entry.places = _join_list(updates.get("places"))

        if text_updated:
            new_text = entry.content or entry.original_text or ""
            entry.word_count = len(new_text.split()) if new_text else 0
            if new_text:
                embedding_vec = entry_service.embed_text(new_text)
                entry.embedding = entry_service.serialize_embedding(embedding_vec)
                if embedding_vec is None:
                    entry.processing_status = "failed"
                    entry.processing_error = "Embedding update failed."
                else:
                    entry.processing_status = "complete"
                    entry.processing_error = None
            else:
                entry.embedding = None
                entry.processing_status = "complete"
                entry.processing_error = None

        entry.updated_at = now
        session.add(entry)
        session.commit()
        session.refresh(entry)

        return {
            "entry_id": entry.id,
            "title": entry.title,
            "content": entry.content,
            "summary": entry.summary,
            "tags": entry.tags or [],
            "memory_type": entry.memory_type.value if hasattr(entry.memory_type, "value") else entry.memory_type,
            "people": _split(entry.people),
            "places": _split(entry.places),
            "confidence_score": entry.confidence_score,
            "last_confirmed_at": entry.last_confirmed_at,
            "updated_at": entry.updated_at,
            "is_flagged": entry.is_flagged,
            "flagged_reason": entry.flagged_reason,
            "processing_status": getattr(entry, "processing_status", "complete"),
            "processing_error": getattr(entry, "processing_error", None),
            "message": "Entry updated.",
        }


@router.post("/entries/{entry_id}/confirm")
def confirm_entry(
    entry_id: str,
    confidence_boost: float = 0.05,
    user_id: str = Depends(get_current_user_id),
):
    """
    Mark a memory as confirmed, bumping confidence slightly and setting last_confirmed_at.
    """
    with get_session() as session:
        entry = _get_entry(session, entry_id, user_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found.")

        now = datetime.utcnow()
        current_conf = entry.confidence_score or 0.0
        try:
            boost = max(0.0, float(confidence_boost))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="confidence_boost must be a number.")
        new_conf = min(1.0, current_conf + boost)

        entry.last_confirmed_at = now
        entry.confidence_score = new_conf
        entry.updated_at = now
        session.add(entry)
        session.commit()
        session.refresh(entry)

        return {
            "entry_id": entry.id,
            "confidence_score": entry.confidence_score,
            "last_confirmed_at": entry.last_confirmed_at,
            "updated_at": entry.updated_at,
            "message": "Entry confirmed.",
        }


@router.post("/entries/{entry_id}/flag")
def flag_entry(
    entry_id: str,
    payload: EntryFlagRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Flag or unflag an entry with an optional reason.
    """
    with get_session() as session:
        entry = _get_entry(session, entry_id, user_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found.")

        entry.is_flagged = bool(payload.flagged)
        entry.flagged_reason = payload.reason.strip() if payload.reason else None
        entry.updated_at = datetime.utcnow()
        session.add(entry)
        session.commit()
        session.refresh(entry)

        return {
            "entry_id": entry.id,
            "is_flagged": entry.is_flagged,
            "flagged_reason": entry.flagged_reason,
            "updated_at": entry.updated_at,
            "message": "Entry flag updated.",
        }
