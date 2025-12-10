# LTM Voice Assistant

A lightweight life-story memory tool: record short voice notes, transcribe them with OpenAI, analyze the text, and store the results in SQLite through a FastAPI backend. The bundled HTML UI records audio in the browser and posts it to the backend.

## Features
- FastAPI backend with CORS enabled for local dev.
- Endpoint `POST /entries` accepts audio (`multipart/form-data`) or raw text; audio is transcribed with `gpt-4o-transcribe`.
- Entry analysis via OpenAI (summary, themes, emotions + scores, topics, people/places, memory chunks, word count) using `gpt-4o-mini`.
- Embedding-based retrieval for Q&A using `text-embedding-3-small` to ground answers in the most relevant past entries.
- SQLite persistence via SQLModel (`ltm.db` by default).
- Simple frontend (`frontend/index.html`) with two tabs:
  - **Capture**: record audio and send it to the API.
  - **Insights & Q&A**: browse stored entries with metadata (emotions, topics, entities, word counts), view stats, ask grounded questions, hold a conversation with your memories, and generate weekly/monthly recaps.
- Daily prompt helper at `GET /prompt/daily`.
 
### Insights endpoints (new)
- `GET /insights/entries` – List entries with id, created_at, preview, summary.
- `GET /insights/summary` – Aggregate stats: total_entries, total_words, entries_per_day.
- `POST /insights/query` – `{ "question": "..." }` → `{ "answer": "...", "used_entry_ids": [...] }` using stored entries as context.

## Project Structure
- `main.py` – FastAPI app, mounts routers and serves the static frontend.
- `app/routers/` – API routes (`entries`, `health`, `prompts`, `insights`, `conversation`).
- `app/services/` – Transcription, OpenAI analysis, and entry handling.
- `app/db/` – Database setup and session helper.
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
pip install fastapi uvicorn[standard] sqlmodel python-dotenv openai
# Additional tooling (migrations/tests):
pip install alembic pytest pydantic-settings
```

Create a `.env` file:
```
OPENAI_API_KEY=your_key_here
# Optional: DATABASE_URL=sqlite:///./ltm.db
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
- **Insights & Q&A tab:** automatically fetches `/insights/entries` and `/insights/summary`, and lets you ask questions via `/insights/query`.

## API Quick Reference
- `POST /entries` – Form data: `file` (audio) or `text` (string). Returns stored entry info + analysis.
- `GET /prompt/daily` – Returns a generated daily reflection prompt.
- `GET /insights/entries` – Entry previews for the Insights tab.
- `GET /insights/summary` – Aggregate stats.
- `POST /insights/query` – Ask a question grounded in stored entries.
- `POST /conversation/respond` – Send a conversational message with history; returns a grounded reply and referenced entry ids.
- `GET /insights/weekly` – Weekly recap (summary, themes, highlights, mood trajectory).
- `GET /insights/monthly` – Monthly recap (summary, themes, highlights, mood trajectory).
- `GET /health` – Basic health check.

## Notes
- The backend uses OpenAI; make sure the `.env` file is loaded before running.
- `ltm.db` is ignored by git; delete it if you want a fresh database.
- Update CORS or host settings in `main.py` if you deploy beyond local dev.

## Configuration
- Managed via Pydantic settings in `app/core/config.py` (loads `.env`).
- Key env vars: `OPENAI_API_KEY`, `DATABASE_URL` (defaults to `sqlite:///./ltm.db`), `ENVIRONMENT`.

## Database migrations
- Alembic is configured (`alembic.ini`, `migrations/`).
- Create a new revision: `alembic revision --autogenerate -m "message"`.
- Apply migrations: `alembic upgrade head`.

## Tests
- Basic pytest suite exercises entry creation, insights summary, and Q&A (`tests/test_api.py`).
- Run with: `pytest`
