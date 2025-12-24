from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlmodel import Session

from app.db.database import get_session
from app.models.entry import Entry
from app.core.auth import get_current_user_id
from app.services.entry_service import process_entry

router = APIRouter()

@router.post("/entries")
async def add_entry(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    source: Optional[str] = Form(None),
    confidence_score: Optional[float] = Form(None),
    user_id: str = Depends(get_current_user_id),
):
    """
    Accepts text OR audio.
    """
    try:
        return await process_entry(
            text=text,
            file=file,
            user_id=user_id,
            source=source,
            confidence_score=confidence_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
        entry = session.get(Entry, entry_id)
        if not entry or entry.user_id != user_id:
            raise HTTPException(status_code=404, detail="Entry not found.")

        now = datetime.utcnow()
        current_conf = entry.confidence_score or 0.0
        new_conf = min(1.0, current_conf + max(0.0, float(confidence_boost)))

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
