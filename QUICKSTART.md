# 🎬 BrainRotStudy Setup Guide

## What Was Just Implemented

Your project now has **6 major upgrades** that align it with raena.ai/brainrot:

✅ **Personality Modes UI** - Users can select UNHINGED, ASMR, GOSSIP, PROFESSOR styles  
✅ **Gemini API Integration** - Free AI script generation (no cost)  
✅ **Better Document Support** - DOCX, XLSX, plus improved captions  
✅ **Smart Image Fetching** - Pexels API fallback for better visuals  
✅ **Quiz Generation** - LLM-powered multiple-choice questions  
✅ **Smart Summaries** - LLM-enhanced study notes  

---

## 🚀 Quick Start (5 minutes)

### Step 1: Get Your Gemini API Key (FREE)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable **Google AI Studio** or **Generative AI API**
4. Create API key at [ai.google.dev](https://ai.google.dev/tutorials/setup)
5. Copy the key

### Step 2: Configure Environment

```bash
# Copy the template
cp .env.example .env

# Edit .env with your favorite editor
# Set these (required):
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your_key_here

# Optional (for better images):
PEXELS_API_KEY=get_free_key_at_pexels.com/api

# Optional (for premium voices):
ELEVENLABS_API_KEY=your_elevenlabs_key
```

### Step 3: Run

```bash
# Build and start
docker-compose up --build

# Wait for services to start (1-2 minutes)
# Access at: http://localhost:3000
```

### Step 4: Test

Try one of these:
- **Upload a PDF** of lecture notes
- **Enter topic:** "Photosynthesis for MCAT"
- **Select style:** Click "UNHINGED" to see Gen-Z chaos mode
- **Watch it build:** 8-stage progress bar in real-time

---

## 💰 Cost Breakdown

| Component | Cost | Notes |
|-----------|------|-------|
| Gemini API | **$0** | Free tier: 1500 requests/day, 1M tokens/min |
| gTTS (Voice) | **$0** | Built-in, robotic but works |
| Pexels (Images) | **$0** | Free tier: 200 req/hour |
| Whisper (Captions) | **$0** | Open source, runs locally |
| Docker (Hosting) | **$0** | Self-hosted locally |
| **TOTAL** | **$0** | ✅ Zero cost to run |

**Optional upgrades:**
- ElevenLabs TTS: $5/mo for natural voices
- GPT-4 instead of Gemini: +$0.03 per video
- Cloud hosting: $5-20/mo

---

## 📁 What Changed

**New Files:**
- `apps/worker/stages/quiz.py` - Quiz generation engine

**Modified Files:**
- `apps/web/app/page.tsx` - Added style selector dropdown
- `apps/worker/stages/script.py` - Added Gemini support
- `apps/worker/stages/assets.py` - Added Pexels API
- `apps/worker/stages/finalize.py` - LLM-powered summaries
- `apps/worker/requirements.txt` - New dependencies
- `docker-compose.yml` - Environment variables
- `.env.example` - Configuration template
- `IMPLEMENTATION.md` - Full technical summary

---

## 🎨 New Features in Action

### 1. Personality Modes

Go to **Advanced Settings** and select:

- **STANDARD** → "Today we're covering mitochondria, the powerhouse..."
- **UNHINGED** → "yo THE MITOCHONDRIA IS ABSOLUTELY BUSSIN NO CAP FR FR"
- **ASMR** → *whispers* "let me softly explain... the mitochondria..."
- **GOSSIP** → "ok girl, let me tell you the TEA about mitochondria..."
- **PROFESSOR** → "It is important to note that mitochondria serves..."

### 2. Export Formats

After video generates, download:
- `final.mp4` - The video
- `notes.md` - Study notes (now LLM-enhanced!)
- `anki.csv` - Flashcards for Anki
- `quiz.json` - Multiple choice questions
- `captions.srt` - Subtitle file
- `metadata.json` - Video info

### 3. LLM Provider Selection

In `.env`:
```env
# Choose ONE:
LLM_PROVIDER=gemini          # Free tier (recommended)
LLM_PROVIDER=openai          # $0.15/1M tokens
LLM_PROVIDER=anthropic       # $0.25/1M tokens
```

---

## ⚙️ Environment Variables Explained

```env
# Core LLM (pick one)
LLM_PROVIDER=gemini              # Which AI to use
GOOGLE_API_KEY=...               # Gemini key
GEMINI_MODEL=gemini-1.5-flash    # Model choice

# Voice (optional)
ELEVENLABS_API_KEY=...           # Premium voices ($5/mo)
# Falls back to gTTS (free) if not set

# Images (optional)
PEXELS_API_KEY=...               # Better stock photos
OPENVERSE_API_TOKEN=...          # Creative Commons

# Infrastructure
REDIS_URL=redis://redis:6379/0   # Job queue
STORAGE_ROOT=/app/storage        # Video storage

# Other
NODE_ENV=production              # Web app mode
API_URL=http://api:8000          # API endpoint
```

---

## 🧪 Testing Checklist

After setup, verify:

- [ ] Web UI loads at http://localhost:3000
- [ ] Can upload a PDF
- [ ] Can enter a topic
- [ ] Can select UNHINGED style
- [ ] Progress bar shows 8 stages
- [ ] Video appears in output
- [ ] Download works
- [ ] Quiz.json exists in output folder
- [ ] Notes.md has LLM content (not just fallback)

---

## 🐛 Troubleshooting

### "Invalid API Key"
- Check `.env` has `GOOGLE_API_KEY=` not `GOOGLE_API_KEY=""` (empty values cause issues)
- Verify key works at: `https://ai.google.dev/tutorials/setup`

### "No images in video"
- Pexels API key might be missing or rate-limited
- Falls back to generated title cards (still works)
- Check `storage/jobs/{job_id}/log.txt` for details

### "Quiz not generating"
- Quiz is optional feature that runs after video
- Check if `export_extras=true` in request
- Review worker logs for LLM errors

### "Slow script generation"
- Gemini 1.5 Flash is slower than Flash-0 variant
- Try: `GEMINI_MODEL=gemini-1.5-flash-0` (if available)
- Or switch to OpenAI: `LLM_PROVIDER=openai`

---

## 📚 Feature Roadmap

### Already Implemented ✅
- [x] 5 personality modes
- [x] Gemini API
- [x] Better document support
- [x] Quiz generation
- [x] Smart summaries

### Coming Soon (Optional)
- [ ] Quiz UI display in web app
- [ ] Language support (select language dropdown)
- [ ] Background video loops (add to `assets/bg_loops/`)
- [ ] Music tracks (add to `assets/music/`)
- [ ] User authentication
- [ ] AI Tutor chat

---

## 🆘 Need Help?

**For API issues:**
- Gemini: https://ai.google.dev/tutorials/setup
- Pexels: https://www.pexels.com/api/
- OpenAI: https://platform.openai.com/account/api-keys

**For code questions:**
- Check `IMPLEMENTATION.md` for technical details
- Review `apps/worker/stages/` for stage pipeline
- See `docker-compose.yml` for service configuration

**For bugs:**
- Check `storage/jobs/{job_id}/log.txt` for errors
- Run syntax check: `python -m py_compile apps/worker/stages/*.py`
- Check Docker logs: `docker-compose logs worker`

---

## 🎯 Next Steps

1. **Test with Gemini** - Follow quick start above
2. **Customize branding** - Edit `apps/web/app/page.tsx` hero text
3. **Add background assets** - Drop video/music files in `assets/` folders
4. **Deploy** - Use Docker image or deploy to cloud (AWS/Azure/GCP)
5. **Monitor** - Set up logging and error tracking

---

**Ready to generate some brainrot videos?** 🚀

Start at: `http://localhost:3000`
