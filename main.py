"""
Word of the Day Pipeline — Phase 1 & 2
Phase 1: Scrapes Dictionary.com WOTD, generates a video script via Claude, outputs data_bridge.json.
Phase 2: TTS via ElevenLabs, Motion Canvas render, FFmpeg merge to final MP4.
"""

import argparse
import json
import os
import random
import shutil
import smtplib
import subprocess
import sys
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth


load_dotenv()

WOTD_URL = "https://www.dictionary.com/e/word-of-the-day/"
FALLBACK_PATH = "local_fallback.json"
OUTPUT_PATH = "data_bridge.json"
TEMP_DIR = "temp"
AUDIO_PATH = os.path.join(TEMP_DIR, "audio.mp3")
EXPORTS_DIR = "exports"
EXPORT_PATH = os.path.join(EXPORTS_DIR, "word_of_the_day.mp4")
COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_WORKFLOW_PATH = "comfyui_workflow.json"
COMFYUI_VIDEO_PATH = os.path.join(TEMP_DIR, "comfyui_raw.mp4")


# ── Fetcher ──────────────────────────────────────────────────────────────────

def send_alert(subject: str, body: str) -> None:
    """Send an email alert via SMTP (Gmail). Fails silently if creds missing."""
    user = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    recipient = os.getenv("RECIPIENT_EMAIL")
    if not all([user, password, recipient]):
        print("[ALERT] Email creds not configured — skipping email alert.")
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = recipient
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user, password)
            server.send_message(msg)
        print(f"[ALERT] Email sent to {recipient}")
    except Exception as e:
        print(f"[ALERT] Failed to send email: {e}")


def load_fallback() -> dict:
    """Return a random entry from local_fallback.json."""
    with open(FALLBACK_PATH, "r") as f:
        entries = json.load(f)
    entry = random.choice(entries)
    print(f"[FALLBACK] Using local word: {entry['word']}")
    return entry


def fetch_word_of_the_day() -> dict:
    """
    Scrape Dictionary.com WOTD using Playwright + stealth.
    Returns dict with keys: word, phonetic, definitions.
    Falls back to local JSON on any failure.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            stealth = Stealth()
            stealth.apply_stealth_sync(context)
            page = context.new_page()
            page.goto(WOTD_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Strategy 1: Parse the embedded JSON data (most reliable)
            json_el = page.query_selector("script#json-current-wotd")
            if json_el:
                import re
                wotd_data = json.loads(json_el.inner_text())
                word = wotd_data["headword"].strip().lower()
                phonetic_html = wotd_data.get("pronunciation", {}).get("phonetic", {}).get("html", "")
                phonetic = f"[{re.sub(r'<[^>]+>', '', phonetic_html)}]" if phonetic_html else ""
                definition = wotd_data.get("definition", "")
                pos = wotd_data.get("partOfSpeech", "")
                definitions = []
                if pos and definition:
                    definitions.append(f"({pos}) {definition}")
                elif definition:
                    definitions.append(definition)

                # Grab example sentence and explanation from top-level JSON fields
                example_html = wotd_data.get("exampleSentence", "")
                if example_html:
                    example = re.sub(r'<[^>]+>', '', example_html).strip()
                    definitions.append(f"Example: {example}")
                body_html = wotd_data.get("body", "")
                if body_html:
                    explanation = re.sub(r'<[^>]+>', '', body_html).strip()
                    definitions.append(explanation)

                browser.close()

                while len(definitions) < 3:
                    definitions.append(f"Used in context: The word '{word}' enriches any sentence.")
                definitions = definitions[:3]

                print(f"[FETCHER] Scraped (JSON): {word} ({phonetic}), {len(definitions)} definitions")
                return {"word": word, "phonetic": phonetic, "definitions": definitions}

            # Strategy 2: DOM scraping fallback with current selectors
            word_el = page.query_selector("a.wotd-entry-headword")
            if not word_el:
                raise ValueError("Could not locate WOTD heading element")
            word = word_el.inner_text().strip().lower()

            phonetic = ""
            phonetic_el = page.query_selector("p.wotd-entry-phonetics")
            if phonetic_el:
                phonetic = phonetic_el.inner_text().strip()

            definitions = []
            def_el = page.query_selector("p.wotd-entry-definition")
            pos_el = page.query_selector("div.wotd-entry-pos")
            if def_el:
                pos = pos_el.inner_text().strip() if pos_el else ""
                defn = def_el.inner_text().strip()
                definitions.append(f"({pos}) {defn}" if pos else defn)

            example_el = page.query_selector("p.wotd-entry-example")
            if example_el:
                definitions.append(f"Example: {example_el.inner_text().strip()}")

            explanation_el = page.query_selector("div.wotd-entry-explanation-section p")
            if explanation_el:
                definitions.append(explanation_el.inner_text().strip())

            browser.close()

            if not word or len(definitions) < 1:
                raise ValueError(f"Incomplete data — word='{word}', defs={len(definitions)}")

            while len(definitions) < 3:
                definitions.append(f"Used in context: The word '{word}' enriches any sentence.")
            definitions = definitions[:3]

            print(f"[FETCHER] Scraped (DOM): {word} ({phonetic}), {len(definitions)} definitions")
            return {"word": word, "phonetic": phonetic, "definitions": definitions}

    except Exception as e:
        print(f"[FETCHER] Scraping failed: {e}")
        send_alert(
            subject="WOTD Scraper Failed",
            body=f"The Dictionary.com scraper encountered an error:\n\n{e}\n\nFalling back to local data.",
        )
        return load_fallback()


# ── Writer ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a witty scientific communicator. "
    "Use the provided word and 3 definitions to write a 15-second script. "
    "Tone: Fast-paced, high-intelligence, slightly snarky."
)

OUTPUT_SCHEMA = {
    "word": "string — the word of the day",
    "definitions": "list of 3 definition strings",
    "narration": "string — max 240 characters, the spoken script",
    "on_screen_text": "list of exactly 2 short punchy phrases",
    "background_hex": "a dark, cinematic hex color code (e.g. #1a1a2e)",
}


def generate_script(word_data: dict) -> dict:
    """Call Claude via the claude CLI to generate a video script from the WOTD data."""
    prompt = (
        SYSTEM_PROMPT + "\n\n"
        f"Word: {word_data['word']}\n"
        f"Phonetic: {word_data['phonetic']}\n"
        f"Definitions:\n"
        + "\n".join(f"  {i+1}. {d}" for i, d in enumerate(word_data["definitions"]))
        + "\n\n"
        "Return ONLY valid JSON with these exact keys:\n"
        + json.dumps(OUTPUT_SCHEMA, indent=2)
        + "\n\nConstraints:\n"
        "- narration must be <= 240 characters\n"
        "- on_screen_text must have exactly 2 items\n"
        "- background_hex must be a dark color (value < #444444)\n"
        "- No markdown fences, no commentary — raw JSON only."
    )

    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
    result = subprocess.run(
        ["claude", "-p", "--model", "claude-haiku-4-5-20251001"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed (exit {result.returncode}): {result.stderr}")

    raw = result.stdout.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
        raw = raw.strip()

    parsed = json.loads(raw)

    # Validate
    assert isinstance(parsed.get("word"), str), "word must be a string"
    assert isinstance(parsed.get("definitions"), list) and len(parsed["definitions"]) == 3
    assert isinstance(parsed.get("narration"), str) and len(parsed["narration"]) <= 240
    assert isinstance(parsed.get("on_screen_text"), list) and len(parsed["on_screen_text"]) == 2
    assert isinstance(parsed.get("background_hex"), str) and parsed["background_hex"].startswith("#")

    return parsed


# ── Phase 2: Audio Engine ─────────────────────────────────────────────────────

def generate_audio() -> None:
    """Send narration from data_bridge.json to ElevenLabs TTS (Voice: George). Save to temp/audio.mp3."""
    from elevenlabs.client import ElevenLabs

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key or api_key == "your_elevenlabs_api_key_here":
        raise RuntimeError("ELEVENLABS_API_KEY not set in .env")

    with open(OUTPUT_PATH, "r") as f:
        data = json.load(f)

    narration = data["narration"]
    print(f"[AUDIO] Narration ({len(narration)} chars): {narration[:80]}...")

    client = ElevenLabs(api_key=api_key)

    os.makedirs(TEMP_DIR, exist_ok=True)

    audio_generator = client.text_to_speech.convert(
        # voice_id="mFgXOmlOfXfr6suoQkRH",  # George
        voice_id="onwK4e9ZLuTAKqWW03F9",
        text=narration,
        model_id="eleven_multilingual_v2",
    )

    with open(AUDIO_PATH, "wb") as f:
        for chunk in audio_generator:
            f.write(chunk)

    size = os.path.getsize(AUDIO_PATH)
    print(f"[AUDIO] Saved to {AUDIO_PATH} ({size:,} bytes)")


# ── Phase 2: ComfyUI Render ───────────────────────────────────────────────────

def render_comfyui() -> None:
    """Submit workflow to ComfyUI API, poll until done, download output video.
    Output saved to temp/comfyui_raw.mp4.
    """
    import time
    import urllib.request
    import urllib.parse

    with open(OUTPUT_PATH, "r") as f:
        data = json.load(f)

    word = data["word"]
    phonetic = data.get("phonetic", "")
    definition = data["definitions"][0]

    prompt_text = (
        f"close-up cinematic photograph, a human hand holding a black pen writing on a nude beige sticky note, "
        f"the sticky note shows the word '{word}' in large handwritten letters at the top, "
        f"below it '{phonetic}' in smaller handwritten script, "
        f"below that a short definition '{definition}' in neat handwriting, "
        f"warm natural window light, shallow depth of field, photorealistic, 4k, high detail"
    )

    with open(COMFYUI_WORKFLOW_PATH, "r") as f:
        workflow_template = f.read()

    escaped_prompt = prompt_text.replace("\\", "\\\\").replace('"', '\\"')
    workflow_json = workflow_template.replace("{{PROMPT_TEXT}}", escaped_prompt)
    workflow = json.loads(workflow_json)

    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    print(f"[COMFYUI] Submitting workflow for word: {word}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    prompt_id = result.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return a prompt_id: {result}")
    print(f"[COMFYUI] Queued. prompt_id={prompt_id}")

    poll_interval = 10
    max_wait = 1800  # 30 minutes (Wan I2V is slow on Apple Silicon)
    elapsed = 0
    output_filename = None
    output_subfolder = ""

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        with urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}", timeout=15) as resp:
            history = json.loads(resp.read())

        if prompt_id not in history:
            print(f"[COMFYUI] Waiting... ({elapsed}s elapsed)")
            continue

        job = history[prompt_id]
        status = job.get("status", {})

        if status.get("status_str") == "error":
            raise RuntimeError(f"ComfyUI job failed: {status.get('messages', [])}")

        outputs = job.get("outputs", {})
        for node_id, node_output in outputs.items():
            for file_entry in node_output.get("videos", []):
                output_filename = file_entry["filename"]
                output_subfolder = file_entry.get("subfolder", "")
                break
            if output_filename:
                break

        if output_filename:
            print(f"[COMFYUI] Done after {elapsed}s. Output: {output_filename}")
            break

        print(f"[COMFYUI] Still running... ({elapsed}s elapsed)")

    if not output_filename:
        raise RuntimeError(f"ComfyUI job did not complete within {max_wait}s")

    params = urllib.parse.urlencode({
        "filename": output_filename,
        "subfolder": output_subfolder,
        "type": "output",
    })
    download_url = f"{COMFYUI_URL}/view?{params}"

    os.makedirs(TEMP_DIR, exist_ok=True)
    print(f"[COMFYUI] Downloading output video...")
    urllib.request.urlretrieve(download_url, COMFYUI_VIDEO_PATH)

    size = os.path.getsize(COMFYUI_VIDEO_PATH)
    print(f"[COMFYUI] Saved to {COMFYUI_VIDEO_PATH} ({size:,} bytes)")


# ── Phase 2: FFmpeg Merge ─────────────────────────────────────────────────────

def merge_video() -> None:
    """Loop ComfyUI video clip and merge with ElevenLabs audio into final MP4."""
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",        # loop short ComfyUI clip indefinitely
        "-i", COMFYUI_VIDEO_PATH,
        "-i", AUDIO_PATH,
        "-c:v", "h264_videotoolbox", # Apple Silicon hardware encoder
        "-b:v", "8000k",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",                 # trim at end of audio track
        "-movflags", "+faststart",
        EXPORT_PATH,
    ]

    print("[FFMPEG] Merging ComfyUI video + audio...")
    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        print(f"[FFMPEG] stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg merge failed (exit code {result.returncode})")

    size = os.path.getsize(EXPORT_PATH)
    print(f"[FFMPEG] Output: {EXPORT_PATH} ({size:,} bytes / {size / 1_048_576:.1f} MB)")


# ── Phase 2: Cleanup Manager ─────────────────────────────────────────────────

def cleanup() -> None:
    """Delete temp/ only if exports/word_of_the_day.mp4 exists and is > 1MB."""
    if not os.path.isfile(EXPORT_PATH):
        print("[CLEANUP] Skipped — export file not found.")
        return

    size = os.path.getsize(EXPORT_PATH)
    if size < 1_048_576:
        print(f"[CLEANUP] Skipped — export is only {size:,} bytes (< 1MB).")
        return

    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print(f"[CLEANUP] Removed {TEMP_DIR}/ (export verified: {size:,} bytes)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Word of the Day Pipeline")
    parser.add_argument(
        "--test", action="store_true",
        help="Test mode: skip Claude and ElevenLabs API calls, reuse cached data_bridge.json and temp/audio.mp3",
    )
    args = parser.parse_args()

    test_mode = args.test

    print("=" * 60)
    print("  WORD OF THE DAY PIPELINE — Phase 1 & 2")
    if test_mode:
        print("  *** TEST MODE — skipping API calls ***")
    print("=" * 60)

    # ── Phase 1 ──
    if test_mode:
        if not os.path.isfile(OUTPUT_PATH):
            raise RuntimeError(f"Test mode requires existing {OUTPUT_PATH}")
        print(f"\n[1/5] Skipping fetch — using cached {OUTPUT_PATH}")
        print(f"\n[2/5] Skipping Claude — using cached {OUTPUT_PATH}")
        with open(OUTPUT_PATH, "r") as f:
            script = json.load(f)
        print(json.dumps(script, indent=2))
    else:
        print("\n[1/5] Fetching Word of the Day...")
        word_data = fetch_word_of_the_day()

        print("\n[2/5] Generating script via Claude...")
        script = generate_script(word_data)
        script["phonetic"] = word_data.get("phonetic", "")

        with open(OUTPUT_PATH, "w") as f:
            json.dump(script, f, indent=2)
        print(f"[DONE] Output saved to {OUTPUT_PATH}")
        print(json.dumps(script, indent=2))

    # ── Phase 2 ──
    if test_mode:
        if not os.path.isfile(AUDIO_PATH):
            raise RuntimeError(f"Test mode requires existing {AUDIO_PATH}")
        print(f"\n[3/5] Skipping TTS — using cached {AUDIO_PATH}")
    else:
        print("\n[3/5] Generating TTS audio via ElevenLabs...")
        generate_audio()

    print("\n[4/5] Generating video via ComfyUI API...")
    render_comfyui()

    print("\n[5/5] Merging ComfyUI video + audio via FFmpeg (Apple Silicon)...")
    merge_video()

    # Cleanup
    cleanup()

    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print(f"  Output: {EXPORT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
