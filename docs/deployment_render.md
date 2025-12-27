# Deployment Guide (Free-tier friendly)

This guide deploys the FastAPI backend **and** the static frontend together as a single Render web service with a managed Postgres database. It’s the simplest low-cost setup for a small public user base.

## Why Render + Postgres?
- **Single deploy**: `main.py` already serves the frontend at `/`.
- **Cheap/free**: Render’s free tiers are fine for early usage.
- **Reliable storage**: Postgres handles multiple concurrent users safely (SQLite does not).

---

## 1) Create a Postgres database
1. In Render, create a **PostgreSQL** instance.
2. Copy the `DATABASE_URL` connection string.

> You can also use Supabase Postgres if you prefer; the app just needs a standard `DATABASE_URL`.

---

## 2) Create a Render web service
1. Create a new **Web Service** from your Git repo.
2. Set the **Build Command**:
   ```bash
   pip install fastapi uvicorn[standard] sqlmodel python-dotenv openai psycopg[binary] alembic pytest pydantic-settings passlib[bcrypt] python-jose
   ```
3. Set the **Start Command**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 10000
   ```

---

## 3) Environment variables
Set these in Render:

```
OPENAI_API_KEY=your_key
DATABASE_URL=postgresql+psycopg://...
ENVIRONMENT=production
JWT_SECRET_KEY=your-long-random-secret
ALLOWED_ORIGINS=https://your-render-app.onrender.com
```

Notes:
- `ALLOWED_ORIGINS` should include your frontend URL(s).
- `JWT_SECRET_KEY` should be a long random string.

---

## 4) Run migrations
Run Alembic migrations once:
```bash
alembic upgrade head
```
Render supports a **Post-deploy Command** where you can run this automatically.

---

## 5) Access your app
Your public URL (from Render) now serves the frontend at `/`.

Users can:
1. Create accounts on the page.
2. Log in.
3. Record entries and retrieve them later.

---

## Optional: Custom domains + HTTPS
Render can attach a custom domain with HTTPS automatically.
