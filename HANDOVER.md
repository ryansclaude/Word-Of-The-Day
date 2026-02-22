# HANDOVER — Word of the Day Video Pipeline

## Status: Phase 3 Implemented. Approval gate & social distribution ready.

---

## Directory Structure

```
ClaudeSurvival/
├── .env                          # API keys (ANTHROPIC, ELEVENLABS, email)
├── main.py                       # Full pipeline: Fetcher → Writer → TTS → Render → Merge
├── local_fallback.json           # 2 fallback WOTD entries if scraping fails
├── data_bridge.json              # OUTPUT — generated after Phase 1
├── HANDOVER.md                   # This file
├── venv/                         # Python 3 virtual environment
├── motion-canvas/                # Motion Canvas animation project
│   ├── src/
│   │   ├── project.ts            # Project entry point
│   │   └── scenes/scene.tsx      # 9:16 animation (1080x1920, 15s)
│   ├── render.mjs                # Headless Puppeteer render script
│   ├── vite.config.ts            # Vite + Motion Canvas plugin config
│   ├── tsconfig.json             # TypeScript config
│   └── package.json              # Node dependencies
├── temp/                         # Transient (audio.mp3, frames/) — auto-cleaned
└── exports/
    └── word_of_the_day.mp4       # Final 9:16 video output
```

## How to Run

```bash
# Set your API keys in .env first:
#   ANTHROPIC_API_KEY=sk-...
#   ELEVENLABS_API_KEY=...

# Install dependencies (first time only)
cd motion-canvas && npm install && cd ..
source venv/bin/activate
pip install elevenlabs ffmpeg-python

# Run the full pipeline
python main.py
```

## `data_bridge.json` Schema

```json
{
  "word": "string — the word of the day",
  "definitions": ["string", "string", "string"],
  "narration": "string — max 240 chars, the spoken 15-second script",
  "on_screen_text": ["short phrase 1", "short phrase 2"],
  "background_hex": "#1a1a2e (dark cinematic hex code)"
}
```

| Field            | Type         | Constraints                         |
|------------------|--------------|-------------------------------------|
| `word`           | `string`     | Lowercase, single word              |
| `definitions`    | `list[str]`  | Exactly 3 items                     |
| `narration`      | `string`     | Max 240 characters                  |
| `on_screen_text` | `list[str]`  | Exactly 2 short punchy phrases      |
| `background_hex` | `string`     | Dark hex color, starts with `#`     |

## Pipeline Flow

```
Dictionary.com ──► Fetcher (Playwright + stealth)
       │                    │
       │ (fail)             │ (success)
       ▼                    ▼
  local_fallback.json    word_data{word, phonetic, definitions}
       │                    │
       └────────┬───────────┘
                ▼
         Writer (Claude Haiku)
                │
                ▼
        data_bridge.json
                │
        ┌───────┴───────┐
        ▼               ▼
   ElevenLabs TTS    Motion Canvas
   (Voice: George)   (Puppeteer headless)
   temp/audio.mp3    temp/frames/*.png
        │               │
        └───────┬───────┘
                ▼
        FFmpeg (M2 h264_videotoolbox)
                │
                ▼
        exports/word_of_the_day.mp4
                │
                ▼
        Cleanup (delete temp/ if export > 1MB)
```

## FFmpeg Command (M2 Silicon)

```bash
ffmpeg -y \
  -framerate 30 \
  -i temp/frames/frame%06d.png \
  -i temp/audio.mp3 \
  -c:v h264_videotoolbox \
  -b:v 8000k \
  -pix_fmt yuv420p \
  -c:a aac \
  -b:a 192k \
  -shortest \
  exports/word_of_the_day.mp4
```

**Critical M2 Flags:**
- `-c:v h264_videotoolbox` — Apple Silicon hardware acceleration
- `-b:v 8000k` — High bitrate for social media quality
- `-pix_fmt yuv420p` — QuickTime/Mobile compatibility

## Package Versions

### Node (motion-canvas/)
| Package                         | Version |
|---------------------------------|---------|
| `@motion-canvas/core`           | 3.17.2  |
| `@motion-canvas/2d`             | 3.17.2  |
| `@motion-canvas/vite-plugin`    | 3.17.2  |
| `vite`                          | 5.4.21  |
| `puppeteer`                     | 24.37.5 |

### Python (venv/)
| Package          | Version |
|------------------|---------|
| `elevenlabs`     | 2.36.1  |
| `ffmpeg-python`  | 0.2.0   |
| `anthropic`      | (Phase 1)|
| `playwright`     | (Phase 1)|

## Resilience

- If scraping fails, an email alert is sent and pipeline falls back to `local_fallback.json`.
- Claude output is validated against schema before saving.
- Cleanup only runs if export exists and is > 1MB.
- Headless render uses Puppeteer with 2-minute timeout.

---

## Phase 3 — Approval Gate & Social Distribution

### New File: `approve.py`

Runs the approval gate, uploads to TikTok/Instagram, archives, and cleans up.

```bash
# After Phase 1 & 2 complete:
python approve.py
```

### Flow

```
exports/word_of_the_day.mp4
        │
        ▼
  Approval Gate (open in QuickTime → y/n prompt)
        │
   y ───┤──── n → log rejection → exit
        ▼
  Build caption from data_bridge.json
        │
        ├──► TikTok (Direct Post API)
        ├──► Instagram (instagrapi Reels)
        │
        ▼
  Archive to permanent_archive/YYYY-MM-DD/
        │
        ▼
  Cleanup temp/ (frames + audio)
        │
        ▼
  Update HANDOVER.md → "Project Lifecycle: Completed"
```

### Environment Variables (`.env`)

| Variable               | Purpose                                  |
|------------------------|------------------------------------------|
| `TIKTOK_ACCESS_TOKEN`  | TikTok Direct Post API bearer token      |
| `INSTAGRAM_USERNAME`   | Instagram login username                 |
| `INSTAGRAM_PASSWORD`   | Instagram login password                 |

### Dependencies

```bash
pip install instagrapi requests
```

### Retry / Auth Errors

- **TikTok token expired**: Script prints the re-auth URL (`https://developers.tiktok.com/apps/`)
- **Instagram challenge**: Script prompts to log in manually then retry
- Platforms with missing credentials are **skipped**, not errored
