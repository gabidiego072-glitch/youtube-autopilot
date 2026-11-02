# YouTube-Autopilot

AI-powered YouTube automation platform for **Shorts** (vertical 9:16, up to 3 min) and **long-form** videos (horizontal 16:9).

> **Status: foundation (v0.1.0).** The architecture, database, API and core services are in place and tested.
> Nothing is published to YouTube; publishing is disabled by default and the upload itself is not implemented yet.
> See [docs/ROADMAP.md](docs/ROADMAP.md) for what is done and what is next.

## What works today

| Area | Status |
| --- | --- |
| Channels and video projects (Shorts + long-form) | ✅ CRUD API, per-format duration rules, lifecycle state machine |
| Script generation | ✅ Real Claude integration (needs `ANTHROPIC_API_KEY`), versioned scripts |
| Metadata + thumbnail concept | ✅ Claude generates title/description/tags/thumbnail text; checked against YouTube limits |
| Video rendering | ✅ FFmpeg service renders image + audio slideshows at 1080×1920 or 1920×1080, extracts thumbnail frames. ⏳ Render jobs are queued but **no worker runs them yet** |
| YouTube publishing | ⏳ Interface + safety gates only. Always refuses (disabled / not configured / not implemented) |
| Analytics | ✅ Manual metric entry + derived metrics. ⏳ YouTube Analytics API collector not implemented |
| Performance analysis | ✅ Evidence-based insights from stored analytics (minimum sample sizes) |
| Reporting | ✅ Period reports built from the database |
| Dashboard API | ✅ Summary endpoint + honest integration status |

## Tech stack

Python 3.12+ · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL (Supabase) · FFmpeg · Anthropic SDK (Claude)

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # then fill in DATABASE_URL, and ANTHROPIC_API_KEY if you want AI generation
alembic upgrade head          # create the database schema
uvicorn app.main:app --reload
```

Open <http://localhost:8000/docs> for the interactive API.
Check `GET /api/v1/system/integrations` to see which external services are configured.

FFmpeg must be installed (`apt install ffmpeg` / `brew install ffmpeg`).

### Supabase

Use the connection string from **Project Settings → Database**, with the `postgresql+psycopg://` scheme, as `DATABASE_URL`.
Run `alembic upgrade head` against it to create the tables.

## Configuration

All configuration and secrets come from environment variables. See [.env.example](.env.example) for the full list.
In `ENVIRONMENT=production` the app refuses to start without a PostgreSQL `DATABASE_URL` and an `API_KEY`.

When `API_KEY` is set, every `/api/v1` request needs the header `X-API-Key: <key>`. `/health` and `/health/ready` stay open for load balancers.

## Production workflow (API)

```
POST /api/v1/channels                               create a channel
POST /api/v1/projects                               create a Short or long-form project   -> draft
POST /api/v1/projects/{id}/scripts/generate         Claude writes the script               -> script_ready
POST /api/v1/projects/{id}/renders                  queue a render job (worker: Phase 2)
POST /api/v1/projects/{id}/metadata/generate        title, description, tags, thumbnail    -> metadata_ready
POST /api/v1/projects/{id}/approve                  human sign-off (needs a finished render) -> ready_to_publish
POST /api/v1/projects/{id}/publish                  refused until Phase 5
POST /api/v1/projects/{id}/analytics                record metrics manually
POST /api/v1/insights/analyze                       find patterns in performance
POST /api/v1/reports                                build a period report
GET  /api/v1/dashboard/summary                      overview for the dashboard
```

## Tests

```bash
pytest                       # SQLite, plus real FFmpeg renders when ffmpeg is installed
ruff check . && ruff format --check .
```

Run against PostgreSQL too (the databases are wiped):

```bash
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost/autopilot_test \
TEST_POSTGRES_URL=postgresql+psycopg://user:pass@localhost/autopilot_migrations \
pytest
```

Tests never call Claude or YouTube. AI responses come from a stub provider defined in `tests/conftest.py`.

## Deployment

The `Dockerfile` builds an image with FFmpeg. Run `alembic upgrade head` as a release step, then start the container; it listens on `$PORT` (default 8000).
CI (`.github/workflows/ci.yml`) runs lint and the full test suite against PostgreSQL 16.

## Project layout

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
