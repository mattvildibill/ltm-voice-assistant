import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from fastapi import BackgroundTasks

from app.services.story_service import generate_weekly_video


PRODUCT_ROOT = Path("products")
WEEKLY_VIDEO_ROOT = PRODUCT_ROOT / "weekly-video"


@dataclass
class ProductJob:
    job_id: str
    user_id: str
    product_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    output_path: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "user_id": self.user_id,
            "product_type": self.product_type,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "output_path": self.output_path,
            "error": self.error,
            "metadata": self.metadata,
        }


_JOBS: Dict[str, ProductJob] = {}


def _job_dir(job_id: str) -> Path:
    return WEEKLY_VIDEO_ROOT / job_id


def _job_file(job_id: str) -> Path:
    return _job_dir(job_id) / "job.json"


def _save_job(job: ProductJob) -> None:
    path = _job_file(job.job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job.to_dict(), indent=2))


def _load_job(job_id: str) -> Optional[ProductJob]:
    path = _job_file(job_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return ProductJob(
        job_id=data["job_id"],
        user_id=data["user_id"],
        product_type=data["product_type"],
        status=data["status"],
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
        output_path=data.get("output_path"),
        error=data.get("error"),
        metadata=data.get("metadata") or {},
    )


def get_job(job_id: str) -> Optional[ProductJob]:
    job = _JOBS.get(job_id)
    if job:
        return job
    job = _load_job(job_id)
    if job:
        _JOBS[job_id] = job
    return job


def _update_job(job: ProductJob, status: str, output_path: Optional[str] = None, error: Optional[str] = None, metadata: Optional[Dict] = None) -> None:
    job.status = status
    job.updated_at = datetime.utcnow()
    if output_path is not None:
        job.output_path = output_path
    if error is not None:
        job.error = error
    if metadata is not None:
        job.metadata = metadata
    _JOBS[job.job_id] = job
    _save_job(job)


def create_weekly_video_job(user_id: str, background_tasks: BackgroundTasks) -> ProductJob:
    PRODUCT_ROOT.mkdir(parents=True, exist_ok=True)
    WEEKLY_VIDEO_ROOT.mkdir(parents=True, exist_ok=True)

    job_id = str(uuid4())
    now = datetime.utcnow()
    job = ProductJob(
        job_id=job_id,
        user_id=user_id,
        product_type="weekly_video",
        status="queued",
        created_at=now,
        updated_at=now,
    )
    _save_job(job)
    _JOBS[job_id] = job

    background_tasks.add_task(_run_weekly_video_job, job_id, user_id)
    return job


def _run_weekly_video_job(job_id: str, user_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    _update_job(job, status="running")

    try:
        output_dir = _job_dir(job_id)
        result = generate_weekly_video(user_id=user_id, output_dir=output_dir)
        _update_job(
            job,
            status="complete",
            output_path=result.get("video_path"),
            metadata={
                "title": result.get("title"),
                "duration": result.get("duration"),
                "slides": result.get("slides"),
                "scene_prompts": result.get("scene_prompts"),
            },
        )
    except Exception as exc:
        _update_job(job, status="failed", error=str(exc))
