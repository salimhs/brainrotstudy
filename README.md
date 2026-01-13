# BrainRotStudy 🧠📹

> Turn academic PDFs and slides into 60–90 second TikTok-style study videos

A production-ready MVP that converts documents or topics into vertical, attention-optimized study videos with captions, voice narration, and visual assets.

## ✨ Features

- **PDF/PPTX → Video**: Upload slides and get an engaging video recap
- **Topic → Video**: Just enter a topic and get AI-generated content
- **Real-time Progress**: Watch your video being built with SSE updates
- **Multiple Presets**: FAST (quick cuts), BALANCED (medium pacing), EXAM (slower, clear)
- **Export Extras**: Download notes, SRT captions, and Anki flashcards
- **Dark Theme UI**: Polished Next.js interface with Framer Motion animations

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Docker Compose                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   ┌───────────┐     ┌───────────┐     ┌───────────┐                │
│   │           │     │           │     │           │                │
│   │  Next.js  │────▶│  FastAPI  │────▶│  Celery   │                │
│   │   :3000   │     │   :8000   │     │  Worker   │                │
│   │           │     │           │     │           │                │
│   └───────────┘     └─────┬─────┘     └─────┬─────┘                │
│                           │                   │                       │
│                           │    ┌─────────┐   │                       │
│                           └───▶│  Redis  │◀──┘                       │
│                                │  :6379  │                           │
│                                └─────────┘                           │
│                                     │                                 │
│                           ┌─────────▼─────────┐                      │
│                           │      Storage      │                      │
│                           │   /app/storage    │                      │
│                           └───────────────────┘                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- OpenAI API key (or Anthropic)
- FFmpeg (included in Docker, but needed for local dev)

### 1. Clone and Configure

```bash
git clone https://github.com/salimhs/brainrotstudy.git
cd brainrotstudy

# Copy environment template
cp .env.example .env

# Edit .env and add your API keys
nano .env
```

### 2. Start Everything

```bash
docker compose up --build
```

### 3. Open the App

Visit [http://localhost:3000](http://localhost:3000)

## 📁 Project Structure

```
brainrotstudy/
├── apps/
│   ├── api/              # FastAPI backend
│   │   ├── main.py       # API endpoints
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── worker/           # Celery worker
│   │   ├── celery_app.py
│   │   ├── tasks.py
│   │   ├── pipeline.py
│   │   ├── stages/       # Pipeline stage implementations
│   │   │   ├── extract.py
│   │   │   ├── script.py
│   │   │   ├── timeline.py
│   │   │   ├── assets.py
│   │   │   ├── voice.py
│   │   │   ├── captions.py
│   │   │   ├── render.py
│   │   │   └── finalize.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── web/              # Next.js frontend
│       ├── app/
│       │   ├── page.tsx
│       │   ├── layout.tsx
│       │   └── history/
│       ├── components/
│       ├── lib/
│       ├── Dockerfile
│       └── package.json
├── shared/               # Shared Python models
│   ├── models.py         # Pydantic schemas
│   └── utils.py          # Utility functions
├── storage/              # Local file storage
│   └── jobs/             # Job data directories
├── assets/               # Static assets
│   ├── bg_loops/         # Background video loops
│   └── music/            # Background music tracks
├── docker-compose.yml
├── .env.example
└── README.md
```

## 🔧 Pipeline Stages

Each job goes through these stages:

1. **Extract**: Parse PDF/PPTX, extract text and render images
2. **Script**: Generate narration script using LLM
3. **Timeline**: Convert script to timed segments
4. **Assets**: Fetch CC images from Openverse
5. **Voice**: Generate TTS audio (ElevenLabs/gTTS)
6. **Captions**: Create word-level captions
7. **Render**: Compose final video with FFmpeg
8. **Finalize**: Generate extras (notes, Anki cards)

### Job Directory Structure

```
storage/jobs/{job_id}/
├── input/              # Uploaded files
├── extracted/          # Parsed slides and images
├── llm/                # Generated script
├── assets/             # Downloaded images
├── audio/              # Voice audio
├── captions/           # Caption timings
├── render/             # Video segments
├── output/             # Final outputs
└── logs/               # Processing logs
```

## 📝 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/jobs` | Create new job (file or topic) |
| GET | `/jobs/{id}` | Get job status |
| GET | `/jobs/{id}/events` | SSE progress stream |
| GET | `/jobs/{id}/download` | Download final MP4 |
| DELETE | `/jobs/{id}` | Delete job |

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM to use (openai/anthropic) | openai |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `OPENAI_MODEL` | OpenAI model name | gpt-4o-mini |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS key | - |
| `STORAGE_ROOT` | Storage directory | /app/storage |
| `REDIS_URL` | Redis connection URL | redis://redis:6379/0 |

### Presets

| Preset | Description | Segment Length | Style |
|--------|-------------|----------------|-------|
| FAST | Quick cuts, high energy | 3-5s | Dynamic |
| BALANCED | Medium pacing | 5-8s | Neutral |
| EXAM | Slower, clear explanations | 8-12s | Calm |

## 🎨 Adding Custom Assets

### Background Loops

Add MP4 videos to `assets/bg_loops/`:

```bash
cp my_loop.mp4 assets/bg_loops/
```

### Background Music

Add MP3/WAV tracks to `assets/music/`:

```bash
cp lofi_track.mp3 assets/music/
```

## 🐛 Troubleshooting

### FFmpeg not found

Ensure FFmpeg is installed:
```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt install ffmpeg
```

### Permission issues with storage

```bash
sudo chown -R $USER:$USER storage/
chmod -R 755 storage/
```

### Worker not processing jobs

Check Redis connection:
```bash
docker compose logs redis
docker compose logs worker
```

## 🎯 Resume Bullets

Add these to your resume:

- Built end-to-end video generation pipeline converting academic content to TikTok-style study videos using Python, FFmpeg, and LLM APIs
- Designed monorepo architecture with Next.js frontend, FastAPI backend, and Celery workers processing async media pipelines
- Implemented real-time progress tracking via Server-Sent Events with idempotent stage processing and quality fallbacks
- Created polished dark-themed UI with React, Tailwind CSS, and Framer Motion animations

## 📜 License

MIT

---

Built with ❤️ for studying smarter, not harder.
