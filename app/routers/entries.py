from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional
from app.services.entry_service import process_entry

router = APIRouter()

@router.post("/entries")
async def add_entry(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    Accepts text OR audio.
    """
    return await process_entry(text=text, file=file)
