from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.auth import get_current_user_id
from app.services import product_service

router = APIRouter(prefix="/products", tags=["products"])


class ProductJobResponse(BaseModel):
    job_id: str
    product_type: str
    status: str
    created_at: str
    updated_at: str
    output_path: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[dict] = None
    download_url: Optional[str] = None


@router.post("/weekly-video", response_model=ProductJobResponse)
def create_weekly_video(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    job = product_service.create_weekly_video_job(user_id, background_tasks)
    payload = job.to_dict()
    payload["download_url"] = f"/products/{job.job_id}/download"
    return payload


@router.get("/{job_id}", response_model=ProductJobResponse)
def get_product_job(job_id: str, user_id: str = Depends(get_current_user_id)):
    job = product_service.get_job(job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="Job not found.")
    payload = job.to_dict()
    payload["download_url"] = f"/products/{job.job_id}/download" if job.status == "complete" else None
    return payload


@router.get("/{job_id}/download")
def download_job(job_id: str, user_id: str = Depends(get_current_user_id)):
    job = product_service.get_job(job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != "complete" or not job.output_path:
        raise HTTPException(status_code=409, detail="Video is not ready yet.")

    path = Path(job.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file missing.")

    return FileResponse(path, media_type="video/mp4", filename=path.name)
