from fastapi import APIRouter
from app.services.openai_service import generate_daily_prompt

router = APIRouter()

@router.get("/prompt/daily")
def get_daily_prompt():
    prompt = generate_daily_prompt()
    return {"prompt": prompt}
