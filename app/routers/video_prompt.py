from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.auth import get_current_user_id
from app.db.database import get_session
from app.models.entry import Entry
from app.services import video_prompt

router = APIRouter(prefix="/video", tags=["video"])


class CandidateEntry(BaseModel):
    id: str
    created_at: datetime
    summary: Optional[str] = None
    content: Optional[str] = None
    preview: str
    score: Optional[float] = None


class CandidateResponse(BaseModel):
    significant: List[CandidateEntry] = Field(default_factory=list)
    cinematic: List[CandidateEntry] = Field(default_factory=list)


class BuildPromptRequest(BaseModel):
    entry_ids: List[str]
    duration_seconds: int = 15
    orientation: str = "landscape"
    style: str = "cinematic_realistic"
    preset: Optional[str] = "none"


class ShotResponse(BaseModel):
    shot: int
    description: str
    source_entry_ids: List[str]


class BuildPromptResponse(BaseModel):
    prompt: str
    shots: List[ShotResponse]
    used_entry_ids: List[str]
    redactions: Dict[str, bool]
    debug: Optional[Dict] = None


def get_db_session():
    """Provide a scoped session per request."""
    with get_session() as session:
        yield session


@router.get("/candidates", response_model=CandidateResponse)
def get_video_candidates(
    session: Session = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    now = datetime.utcnow()
    cutoff = now - timedelta(days=180)

    entries = session.exec(
        select(Entry)
        .where(Entry.user_id == user_id, Entry.created_at >= cutoff)
        .order_by(Entry.created_at.desc())
        .limit(500)
    ).all()

    if len(entries) < 10:
        entries = session.exec(
            select(Entry)
            .where(Entry.user_id == user_id)
            .order_by(Entry.created_at.desc())
            .limit(500)
        ).all()

    if not entries:
        return CandidateResponse(significant=[], cinematic=[])

    significant, cinematic = video_prompt.select_candidates(entries, top_n=5, now=now)

    return CandidateResponse(
        significant=[video_prompt.build_candidate_payload(item, "significant") for item in significant],
        cinematic=[video_prompt.build_candidate_payload(item, "cinematic") for item in cinematic],
    )


@router.post("/build_prompt", response_model=BuildPromptResponse)
def build_video_prompt(
    payload: BuildPromptRequest,
    session: Session = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    if not payload.entry_ids:
        raise HTTPException(status_code=400, detail="Select at least one entry.")
    if len(payload.entry_ids) > 10:
        raise HTTPException(status_code=400, detail="Select up to 10 entries.")
    if payload.duration_seconds not in (10, 15):
        raise HTTPException(status_code=400, detail="Duration must be 10 or 15 seconds.")
    if payload.orientation not in ("landscape", "portrait"):
        raise HTTPException(status_code=400, detail="Orientation must be landscape or portrait.")

    entries = session.exec(
        select(Entry).where(Entry.user_id == user_id, Entry.id.in_(payload.entry_ids))
    ).all()
    if not entries:
        raise HTTPException(status_code=404, detail="No matching entries found.")

    entry_map = {entry.id: entry for entry in entries}
    ordered = [entry_map[entry_id] for entry_id in payload.entry_ids if entry_id in entry_map]

    if not ordered:
        raise HTTPException(status_code=404, detail="No matching entries found.")

    result = video_prompt.build_sora_prompt(
        ordered,
        duration_seconds=payload.duration_seconds,
        orientation=payload.orientation,
        style=payload.style,
        preset=payload.preset,
    )

    return BuildPromptResponse(
        prompt=result.prompt,
        shots=[ShotResponse(**shot.__dict__) for shot in result.shots],
        used_entry_ids=result.used_entry_ids,
        redactions=result.redactions,
        debug=result.debug,
    )
