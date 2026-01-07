from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.error_handlers import add_exception_handlers
from app.core.config import settings
from app.routers.entries import router as entries_router
from app.routers.health import router as health_router
from app.routers.prompts import router as prompts_router
from app.routers.insights import router as insights_router
from app.routers.conversation import router as conversation_router
from app.routers.products import router as products_router
from app.routers.video_prompt import router as video_prompt_router
from app.db.database import init_db, migrate_db

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

# Ensure tables and new metadata columns exist
init_db()
migrate_db()

add_exception_handlers(app)

if settings.allowed_origins:
    allowed_origins = [
        origin.strip()
        for origin in settings.allowed_origins.split(",")
        if origin.strip()
    ]
else:
    allowed_origins = ["*"] if settings.environment == "development" else []

# ⭐ ABSOLUTE REQUIRED CORS ⭐
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(entries_router)
app.include_router(health_router)
app.include_router(prompts_router)
app.include_router(insights_router)
app.include_router(conversation_router)
app.include_router(products_router)
app.include_router(video_prompt_router)

# Serve the static UI so hitting "/" doesn't 404
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

@app.get("/", include_in_schema=False)
def serve_frontend():
    """
    Return the vanilla HTML UI when users hit the root URL.
    """
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "UI not found"}
