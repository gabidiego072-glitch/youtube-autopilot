# Architecture

## Layers

```
HTTP (FastAPI routes)  app/api/routes/*        thin: validate input, call services, map errors
        │
Services               app/services/*          business logic; no HTTP, no vendor types leaking out
        │
Integrations           ai/claude.py, rendering/ffmpeg.py, youtube/*   behind small interfaces
        │
Persistence            app/models/* (SQLAlchemy) + alembic/versions/*
```

Rules:

- Routes depend on services; services depend on interfaces (`AIProvider`, `VideoPublisher`, `AnalyticsCollector`), not SDKs.
- External services are injected through FastAPI dependencies (`app/api/deps.py`), so tests replace them without patching.
- A missing credential raises `IntegrationNotConfiguredError` (HTTP 503). An integration whose interface exists but whose implementation is a later phase raises `IntegrationNotImplementedError` (HTTP 501). Nothing returns a fake success.
- All configuration comes from `app/core/config.py` (environment variables).

## Directory map

```
app/
  main.py                     app factory, error handlers
  core/                       settings, domain errors, logging
  db/                         declarative base, naming conventions, engine/session
  models/                     database tables (see below)
  schemas/                    Pydantic request/response models
  api/
    deps.py                   settings, DB session, API-key auth, AI + FFmpeg providers
    routes/                   one module per area (module 10: dashboard API)
  content/profile.py          the channel's editorial definition ("What would happen if...?");
                              every prompt is built from it, and it filters off-topic (gaming) output
  services/
    ideas/                    idea generation, de-duplication and ranking
    research/                 Wikipedia client + research briefs (free)
    factcheck/                scientific review of labelled claims
    scenes/                   storyboard: script scenes -> validated procedural 3D scene specs
    voice/                    Piper TTS (free, offline)
    editing/                  FFmpeg editor: voice-paced shots, subtitles, music ducking
    production/formats.py     Shorts vs long-form specs (modules 1 + 2)
    production/pipeline.py    project lifecycle state machine
    scripts/                  prompts + script generation (module 3)
    rendering/ffmpeg.py       FFmpeg/FFprobe wrapper: encode, audio, subtitles (module 4)
    rendering/blender.py      runs the 3D engines headless (module 4)
    rendering/scene3d.py      scene spec -> Blender frames -> MP4 (module 4)
    metadata/                 metadata generation + YouTube limits (module 5)
    youtube/                  publishing + analytics interfaces (modules 6 + 7)
    analytics/metrics.py      derived metrics (module 7)
    learning/analyzer.py      performance analysis (module 8)
    reporting/builder.py      reports (module 9)
render_engines/               procedural 3D engine for Blender: renders every visual (see docs/3D_ENGINES.md)
examples/scenes/              example 3D scene specs
scripts/                      render_3d.py (spec -> MP4), install_blender.sh
alembic/                      migrations
tests/                        pytest suite
```

## Data model

| Table | Purpose |
| --- | --- |
| `channels` | A YouTube channel we produce for: niche, language, style guide |
| `video_projects` | One video, `format` = `short` or `long`, `status` follows the pipeline |
| `scripts` | Versioned scripts: question title, hook, scenes (beat, narration, visual, duration, labelled claims), ending type, visual bible, procedural scene specs, fact-check result |
| `render_jobs` | Render requests with output resolution, status and timing |
| `video_metadata` | Versioned title/description/tags/hashtags/thumbnail concept |
| `media_assets` | Files used or produced (images, clips, voice per scene, final render), linked to script and scene |
| `publish_jobs` | Upload attempts (used from Phase 5) |
| `analytics_snapshots` | Cumulative metrics per video over time; names mirror YouTube Analytics metrics |
| `ideas` | Candidate premises with scores, category and status (new / used / rejected) |
| `research_briefs` | Concepts, Wikipedia sources and key facts per project |
| `insights` | Findings from the analyzer, with evidence |
| `reports` | Generated period reports (JSON content) |

IDs are UUIDs, timestamps are timezone-aware, JSON columns are `JSONB` on PostgreSQL. Enums are stored as `VARCHAR` + `CHECK` so adding a value is a simple migration.

## Project lifecycle

```
draft → script_ready → rendering → rendered → metadata_ready → ready_to_publish → published
                 └──────────────→ metadata_ready (metadata can be written before rendering)
any active state → archived;  rendering / ready_to_publish → failed → draft | script_ready
```

`app/services/production/pipeline.py` holds the full transition table. `ready_to_publish` needs a human approval call plus a finished render and metadata.

## Claude integration

`ClaudeProvider` (`app/services/ai/claude.py`) uses the official `anthropic` SDK:

- model from `CLAUDE_MODEL` (default `claude-opus-5-5`), adaptive thinking, effort from `CLAUDE_EFFORT`
- structured JSON output via `output_config.format` (JSON Schema), validated again with Pydantic
- streaming, so long-form scripts do not hit HTTP timeouts
- server-side refusal fallbacks (`fallbacks: "default"`, beta), switchable with `CLAUDE_SERVER_FALLBACKS`
- refusals, truncation, rate limits and API errors become `ProviderError` (HTTP 502)

Adding another provider means implementing `AIProvider.generate_json` and selecting it in `services/ai/factory.py`.
