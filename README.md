# BrainRotStudy

Turn a PDF, a slide deck, or a bare topic into a 60-second vertical study video
with narration, bold captions, and a Ken-Burns slideshow. One Python service,
one Next.js frontend, FFmpeg for rendering. No Celery, no Redis, no jumpscares.

```
┌──────────┐   HTTP / SSE    ┌────────────────────────┐
│ Next.js  │ ──────────────▶ │ FastAPI + SQLite + bg  │
│ (web/)   │ ◀────────────── │ pipeline (server/)     │ ──▶ FFmpeg, gTTS, LLMs
└──────────┘                 └────────────────────────┘
```

## Quick start

You need **Python 3.11+**, **Node 22+**, and **FFmpeg** on PATH.

```bash
cp .env.example .env
# set at least one of GOOGLE_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY
make install
make dev           # API on :8000, Web on :3000
```

Open <http://localhost:3000>, drop a PDF, hit generate. The video appears
in-place when it's done; study notes + SRT + Anki deck are downloadable too.

## Pipeline

Each job flows through six stages (the UI shows them live):

1. **Extract** — PDF / PPTX / txt / md / raw topic → normalized sections.
2. **Script** — LLM writes an 8-25 word-per-beat JSON narration.
3. **Narrate** — Per-segment TTS. Each clip's duration drives the timeline.
4. **Visuals** — Pexels → Openverse → generated title card (offline-safe).
5. **Render** — FFmpeg stitches a 1080x1920 video with burned-in captions.
6. **Exports** — Markdown notes, SRT, and a Front/Back CSV for Anki.

## Configuration

All config is env-based (see `.env.example`). Sensible defaults mean the only
thing you *must* set is one LLM API key.

| Key                    | Purpose                                      |
| ---------------------- | -------------------------------------------- |
| `GOOGLE_API_KEY`       | Gemini (free tier, default)                  |
| `ANTHROPIC_API_KEY`    | Claude (auto-used if no Gemini key)          |
| `OPENAI_API_KEY`       | GPT-4o-mini (auto-used if no Anthropic key)  |
| `LLM_PROVIDER`         | Force a provider (`auto` by default)         |
| `ELEVENLABS_API_KEY`   | Premium voice (optional, otherwise gTTS)     |
| `PEXELS_API_KEY`       | Stock images (optional, otherwise Openverse) |
| `STORAGE_ROOT`         | Where job artifacts live                     |
| `MAX_CONCURRENT_JOBS`  | How many jobs run in parallel                |

## Development

```bash
make test        # pytest
make typecheck   # tsc --noEmit
make build       # next build
```

### Repo layout

```
server/
  brainrotstudy/
    main.py              FastAPI app
    config.py            Settings
    db.py                SQLite (no ORM)
    events.py            Async pub/sub for SSE
    schemas.py           Pydantic models
    storage.py           Per-job file layout
    pipeline/
      runner.py          Orchestrates stages, publishes progress
      extract.py         PDF/PPTX/text → ExtractedContent
      script.py          LLM → Script JSON (Gemini/Anthropic/OpenAI)
      narrate.py         Per-segment TTS + duration
      visuals.py         Pexels → Openverse → title-card fallback
      render.py          FFmpeg filter graph + SRT writer
      exports.py         Notes (md) + Anki (csv)
  tests/                 pytest, no network, no ffmpeg required
web/
  app/                   Next.js App Router pages
  components/            Form, progress, result, UI primitives
  lib/api.ts             Typed client for the FastAPI server
Dockerfile               One container that runs both services
Makefile                 install / dev / test / build / docker
```

## Docker

```bash
make docker       # builds brainrotstudy:latest, runs on :3000 and :8000
```

The image bundles FFmpeg, the fonts used by the subtitle filter, the Python
server, and the Next.js standalone build.

## Tests

`make test` runs the unit suite:

- Extraction (topic / outline / markdown / PDF path validation)
- LLM provider auto-detection and JSON coercion (with mocked callers)
- Render command composition and SRT serialization (no ffmpeg call)
- Pexels / Openverse / title-card fallback (httpx mocked)
- HTTP contract (FastAPI `TestClient`, pipeline stubbed)
- SQLite CRUD roundtrip

No network, no ffmpeg, no keys required. 28 tests, under a second.

## License

MIT.
