# LTM Voice Assistant

A personal life-story memory tool: record voice notes, transcribe with OpenAI, analyze them into structured memories, and explore them via a timeline, insights, recaps, and chat grounded only in your own entries.

## Features
- FastAPI backend with CORS for local dev + JWT auth.
- Capture: `POST /entries` accepts audio (`multipart/form-data`) or text; audio is transcribed with `gpt-4o-transcribe`.
- Analysis: OpenAI (`gpt-4o-mini`) produces summary, themes, topics, sentiment (label + score), people/places, emotions, memory chunks, word count; embeddings (`text-embedding-3-small`) stored for retrieval.
- Background processing: analysis + embeddings run asynchronously; entries report `processing_status`.
- Retrieval: semantic search powers Q&A and conversation grounded only in stored entries.
- Review workflow: edit entries, confirm memories to boost confidence, and flag incorrect items with reasons.
- Recaps: weekly/monthly recaps synthesized from local stats + entry snippets.
- Persistence: SQLite via SQLModel (`ltm.db` by default) with Alembic migrations.
- Frontend (`frontend/index.html`) with auth and three tabs:
  - **Capture**: recorder + recent entries.
  - **Timeline**: filters (7/30/all) + expandable entry cards with sentiment and topics.
  - **Insights & Chat**: summary stats with entries/day chart, weekly recap, and chat grounded in your memories.
- Daily prompt helper at `GET /prompt/daily`.
 
### Insights endpoints (new)
- `GET /insights/entries` – List entries with id, created_at, preview, summary.
- `GET /insights/summary` – Aggregate stats: total_entries, total_words, entries_per_day.
- `POST /insights/query` – `{ "question": "..." }` → `{ "answer": "...", "used_entry_ids": [...] }` using stored entries as context.

## Project Structure
- `main.py` – FastAPI app, mounts routers and serves the static frontend.
- `app/routers/` – API routes (`entries`, `health`, `prompts`, `insights`, `conversation`).
- `app/services/` – Transcription, OpenAI analysis, entry handling, embeddings.
- `app/db/` – Database setup, session helper.
- `app/models/` – SQLModel entry definition.
- `frontend/` – Vanilla HTML/JS UI for recording and sending entries.
- `app/core/config.py` – Pydantic settings for env vars.
- `app/core/error_handlers.py` – Global exception handling.
- `migrations/` – Alembic migrations.

## Prerequisites
- Python 3.12+
- An OpenAI API key with access to `gpt-4o-mini` and `gpt-4o-transcribe`.

## Setup
```bash
cd /home/mattv/Projects/ltm-lifestory
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install fastapi uvicorn[standard] sqlmodel python-dotenv openai psycopg[binary]
# Additional tooling (migrations/tests/auth):
pip install alembic pytest pydantic-settings passlib[bcrypt] python-jose
# Weekly video generation:
pip install pillow
```

Create a `.env` file:
```
OPENAI_API_KEY=your_key_here
# Optional: DATABASE_URL=sqlite:///./ltm.db
# JWT_SECRET_KEY=dev-secret-change-me
# ALLOWED_ORIGINS=http://localhost:8000
```

# Initialize the database (once) or run migrations:
```bash
alembic upgrade head
```

## Run the backend
```bash
uvicorn main:app --reload
```
API base: `http://127.0.0.1:8000`

## Frontend
- Open `frontend/index.html` in your browser.
- **Capture tab:** click “Start Recording”, then “Stop & Save”. Audio posts to `http://localhost:8000/entries` and shows the analysis response.
- **Timeline tab:** expand an entry to edit, confirm, or flag it and see trust indicators (confidence/last confirmed/updated).
- **Insights & Q&A tab:** automatically fetches `/insights/entries` and `/insights/summary`, and lets you ask questions via `/insights/query`.

## API Quick Reference
- `POST /auth/register` – `{ "email": "...", "password": "..." }` → returns access token + user info.
- `POST /auth/login` – `{ "email": "...", "password": "..." }` → returns access token + user info.
- `POST /entries` – Form data: `file` (audio) or `text` (string). Returns stored entry info + analysis.
- `PATCH /entries/{id}` – Edit title/content/tags/people/places/memory_type/summary.
- `POST /entries/{id}/confirm` – Mark an entry as confirmed (bumps confidence, sets last_confirmed_at).
- `POST /entries/{id}/flag` – Flag/unflag an entry with an optional reason.
- `GET /prompt/daily` – Returns a generated daily reflection prompt.
- `GET /insights/entries` – Entry previews for the Insights tab.
- `GET /insights/summary` – Aggregate stats.
- `POST /insights/query` – Ask a question grounded in stored entries.
- `POST /conversation/respond` – Send a conversational message with history; returns a grounded reply and referenced entry ids.
- `GET /insights/weekly` – Weekly recap (summary, themes, highlights, mood trajectory).
- `GET /insights/monthly` – Monthly recap (summary, themes, highlights, mood trajectory).
- `POST /products/weekly-video` – Generate a 30s weekly recap video (returns job id).
- `GET /products/{job_id}` – Check render status.
- `GET /products/{job_id}/download` – Download the generated MP4.
- `GET /health` – Basic health check.

## Notes
- Only your data: all analysis and retrieval are grounded in your stored entries; no external browsing.
- The backend uses OpenAI; make sure the `.env` file is loaded before running.
- `ltm.db` is ignored by git; delete it if you want a fresh database.
- Update CORS or host settings in `main.py` if you deploy beyond local dev.
- Multi-user scoping: authenticate via `/auth/register` or `/auth/login` and include the `Authorization: Bearer <token>` header on API requests. The frontend handles this automatically.
- Weekly videos require Pillow + ffmpeg installed to render scenes and MP4 output, plus OpenAI image generation.

## Configuration
- Managed via Pydantic settings in `app/core/config.py` (loads `.env`).
- Key env vars: `OPENAI_API_KEY`, `DATABASE_URL` (defaults to `sqlite:///./ltm.db`), `ENVIRONMENT`, `JWT_SECRET_KEY`, `ALLOWED_ORIGINS`.

## Database migrations
- Alembic is configured (`alembic.ini`, `migrations/`).
- Create a new revision: `alembic revision --autogenerate -m "message"`.
- Apply migrations: `alembic upgrade head`.

## Tests
- Basic pytest suite exercises entry creation, insights summary, and Q&A (`tests/test_api.py`).
- Run with: `pytest`

## Manual UI checks
- Timeline: open an entry, click Edit, update title/content/tags, Save → UI + `/insights/entries` reflect changes.
- Timeline: click Confirm memory → confidence/last confirmed update in detail view.
- Timeline: flag an entry with a reason → badge shows flagged status and reason.
- Refresh the page → edits and trust indicators persist.

## Screenshots (placeholders)
- Timeline edit mode: `docs/screenshots/timeline-edit.png`
- Confirm memory action: `docs/screenshots/confirm-memory.png`
- Flagged memory state: `docs/screenshots/flag-memory.png`

## Deployment guide
- See `docs/deployment_render.md` for a free-tier-friendly Render + Postgres setup.

## Seeding fake data (no OpenAI)
- Generate one year of synthetic daily entries without hitting OpenAI:
  ```bash
  python scripts/seed_fake_year.py         # adds on top of existing data
  python scripts/seed_fake_year.py --wipe  # wipes entries first
  ```
  Data is written directly to the DB, so ensure Alembic has run and your `.env`/venv are loaded. 

## Memory schema
- Memory types (`event`, `reflection`, `preference`, `identity`, `project`) and normalized fields are documented in `docs/memory_schema.md`.

## System flow (high level)
```
User (typed/voice)
    │
    ├─► /entries (FastAPI)
    │     ├─ audio? → realtime transcription
    │     ├─ analysis (summary, topics, sentiment, tags)
    │     ├─ embedding (OpenAI)
    │     └─ classify memory_type + source + confidence defaults
    │            ↓
    │         SQLite (SQLModel + Alembic)
    │            ├─ normalized memory fields (id/user/memory_type/title/content/tags)
    │            ├─ trust metadata (source, confidence_score, last_confirmed_at, updated_at)
    │            └─ analysis fields (summary/topics/emotions/embedding/etc.)
    │
    ├─► /entries/{id}/confirm
    │     └─ bump confidence, set last_confirmed_at, update timestamp
    │
    ├─► /insights/query
    │     ├─ candidate gen (top-50 embedding similarity)
    │     ├─ rerank: similarity + recency decay + importance + confidence + domain boost
    │     └─ OpenAI response grounded in reranked memories
    │
    ├─► /conversation/respond
    │     └─ same rerank pipeline → contextual chat
    │
    └─► Frontend (frontend/index.html)
          ├─ Capture tab (record/send)
          ├─ Timeline (recent entries)
          └─ Insights & Chat (summary cards, recaps, Q&A/chat)
```
