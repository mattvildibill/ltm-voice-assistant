# Memory Schema

This project stores each memory as a normalized record so it can be searched, summarized, and grounded in conversations.

## Memory types
- **event**: A specific occurrence in time. Examples: “Went hiking with Jamie today.”, “Met the new PM for kickoff.”
- **reflection**: Introspective thoughts or beliefs. Examples: “I believe I need more rest.”, “I think I handled that conflict better.”
- **preference**: Likes/dislikes, opinions, recurring choices. Examples: “I love early morning runs.”, “I prefer async updates over meetings.”
- **identity**: Statements about self, roles, values. Examples: “I’m a patient parent.”, “As a designer, I focus on clarity.”
- **project**: Work in progress, goals, plans, roadmaps. Examples: “Working on the onboarding revamp.”, “Building a travel budget tracker.”

The classifier is currently heuristic-based (keyword cues) and lives in `app/services/entry_service.py::classify_memory_type`. It can be swapped out for a model later.

## Normalized fields
- `id` (uuid, primary key)
- `user_id` (string, defaults to `default-user` for single-user dev)
- `memory_type` (enum; one of `event|reflection|preference|identity|project`)
- `title` (optional short string)
- `content` (main text body)
- `tags` (optional list of strings; stored as JSON)
- `created_at` (datetime)
- `updated_at` (datetime, auto-updated on changes)
- `last_confirmed_at` (nullable datetime when the user last confirmed it)
- `source` (enum; one of `typed|voice|inferred|external|unknown`)
- `confidence_score` (float in [0,1], defaults by source)
- Additional analysis fields: `summary`, `themes`, `emotions`, `emotion_scores`, `topics`, `people`, `places`, `memory_chunks`, `word_count`, `embedding`, `sentiment_label`, `sentiment_score`, plus `source_type` and `original_text` for ingestion context.

## Backwards compatibility
- The Alembic migration `0003` converts existing integer IDs to UUIDs, adds the new fields, and maps legacy `original_text` into `content`.
- If a legacy row is missing `memory_type`, the app treats it as `event` by default.
- Trust metadata defaults: existing rows get `source="unknown"`, `confidence_score=0.75`, and `updated_at` set to `created_at`.
