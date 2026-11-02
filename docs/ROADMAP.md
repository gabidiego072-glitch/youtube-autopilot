# Development roadmap

Each phase ends with working, tested code. Nothing is marked done until it works against the real service.

## Phase 0 — Foundation ✅ (this release)

- [x] Project structure, configuration from environment variables, Dockerfile, CI
- [x] PostgreSQL/Supabase schema for all 10 modules + Alembic migration (tested on PostgreSQL 16 and SQLite)
- [x] Channels and projects API for Shorts and long-form, with per-format duration rules
- [x] Project lifecycle state machine
- [x] Claude provider (structured output, streaming, refusal fallbacks, error handling)
- [x] Script generation and metadata generation services + endpoints
- [x] YouTube metadata rules (title, description, tag limits)
- [x] FFmpeg service: slideshow render for both formats, probing, frame extraction
- [x] YouTube Data API / Analytics API interfaces with safety gates (publishing disabled by default)
- [x] Manual analytics entry, derived metrics, performance analyzer, reports, dashboard summary
- [x] 53 automated tests (API, services, real FFmpeg renders, migrations)

## Phase 1 — Content quality

- [ ] Topic/idea generation per channel, with deduplication against past videos
- [ ] Script editing endpoint (human edits create a new version)
- [ ] Fact-check / review pass on generated scripts
- [ ] Store token usage and cost per generation; per-channel spending limits
- [ ] Prompt evaluation set to compare prompt versions

## Phase 2 — Rendering pipeline

- [ ] Background job queue and render worker (moves jobs `queued → running → succeeded/failed`, updates project status)
- [ ] Text-to-speech provider interface + first provider (voiceover assets)
- [ ] Visual asset sourcing (stock footage / AI images) per scene
- [ ] Burned-in captions (word-timed for Shorts), background music with ducking
- [ ] Object storage for media (Supabase Storage or S3) instead of local disk

## Phase 3 — Format-specific production

- [ ] Shorts: fast cuts, animated captions, safe areas for the Shorts UI, loop endings
- [ ] Long-form: chapters, section transitions, B-roll, chunked TTS for long scripts
- [ ] Optional: cut Shorts out of long-form videos

## Phase 4 — Thumbnails

- [ ] Image generation provider interface
- [ ] Text overlay compositing at 1280×720
- [ ] Multiple thumbnail variants per video

## Phase 5 — YouTube publishing

- [ ] OAuth 2.0 consent flow to obtain refresh tokens per channel (stored encrypted)
- [ ] Resumable upload via YouTube Data API v3, thumbnail upload, scheduled publishing
- [ ] Quota tracking and retry/backoff
- [ ] Uploads default to `private`; human approval stays required

## Phase 6 — Analytics collection

- [ ] Scheduled collector using the YouTube Analytics API (views, impressions, CTR, retention, subscribers)
- [ ] Audience retention curves per video
- [ ] Backfill for existing channel videos

## Phase 7 — Learning system

- [ ] Feed insights back into topic selection and script prompts
- [ ] Track experiments (hook style, length, posting time) and measure their effect
- [ ] Topic scoring model from past performance

## Phase 8 — Automated reporting

- [ ] Scheduled daily/weekly/monthly reports
- [ ] Delivery by email or Slack
- [ ] Claude-written report summaries on top of the computed numbers

## Phase 9 — Dashboard and multi-user

- [ ] Web dashboard on top of the API
- [ ] User accounts (Supabase Auth) and per-user/channel permissions, replacing the shared API key
- [ ] Row-level security on Supabase

## Phase 10 — Production hardening

- [ ] Structured logging, metrics, tracing, error alerts
- [ ] Rate limiting, request size limits
- [ ] Deployment templates (e.g. Cloud Run / Fly.io / Railway) and backups
