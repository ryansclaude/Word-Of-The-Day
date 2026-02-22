"""
Word of the Day Pipeline — Phase 3: Approval Gate & Social Distribution
Requires: pip install instagrapi requests python-dotenv
"""

import glob
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent
EXPORTS_DIR = PROJECT_ROOT / "exports"
DATA_BRIDGE = PROJECT_ROOT / "data_bridge.json"
HANDOVER_MD = PROJECT_ROOT / "HANDOVER.md"
ARCHIVE_DIR = PROJECT_ROOT / "permanent_archive"
TEMP_DIR = PROJECT_ROOT / "temp"


# ── Helpers ──────────────────────────────────────────────────────────────────

def find_latest_mp4() -> Path:
    """Find the most recently modified .mp4 in exports/."""
    mp4s = sorted(EXPORTS_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4s:
        raise FileNotFoundError(f"No .mp4 files found in {EXPORTS_DIR}")
    return mp4s[0]


def load_data_bridge() -> dict:
    """Load metadata from data_bridge.json."""
    with open(DATA_BRIDGE, "r") as f:
        return json.load(f)


def build_caption(data: dict) -> str:
    """Auto-generate caption + hashtags from data_bridge.json."""
    word = data.get("word", "word")
    on_screen = data.get("on_screen_text", [])
    hook = on_screen[0] if on_screen else ""
    caption = f"{word.capitalize()} — {hook}\n\n"
    caption += "#WordOfTheDay #Vocabulary #LearnEnglish #M2Encoded"
    return caption


# ── 1. Approval Gate ─────────────────────────────────────────────────────────

def approval_gate() -> Path:
    """Locate latest MP4, open in QuickTime for review, prompt for approval."""
    video_path = find_latest_mp4()
    print(f"[Phase 3] Found video: {video_path}")
    print(f"[Phase 3] Opening in QuickTime Player...")

    subprocess.run(["open", str(video_path)])

    while True:
        choice = input("\n[Phase 3] Approve this video for upload? (y/n): ").strip().lower()
        if choice == "y":
            print("[Phase 3] Video APPROVED.")
            return video_path
        elif choice == "n":
            print("[Phase 3] User Rejected Asset.")
            _append_handover("## Rejection Log\n\n"
                             f"- **{datetime.now().isoformat()}**: User rejected video `{video_path.name}`\n")
            sys.exit(0)
        else:
            print("Please enter 'y' or 'n'.")


# ── 2. Social Media Distribution ─────────────────────────────────────────────

def upload_tiktok(video_path: Path, caption: str) -> bool:
    """
    Upload to TikTok via the Direct Post API (Content Posting API).
    Requires TIKTOK_ACCESS_TOKEN in .env.
    Docs: https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
    """
    import requests

    token = os.getenv("TIKTOK_ACCESS_TOKEN")
    if not token or token.startswith("your_"):
        print("[TIKTOK] Skipped — TIKTOK_ACCESS_TOKEN not configured in .env")
        return False

    try:
        # Step 1: Initialize the upload
        init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        file_size = video_path.stat().st_size
        init_body = {
            "post_info": {
                "title": caption[:150],
                "privacy_level": "SELF_ONLY",  # Start as private; change to PUBLIC_TO_EVERYONE when ready
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        }

        resp = requests.post(init_url, headers=headers, json=init_body, timeout=30)
        resp_data = resp.json()

        if resp.status_code == 401 or resp_data.get("error", {}).get("code") == "access_token_invalid":
            print("[TIKTOK] ERROR: Access token expired.")
            print("[TIKTOK] Re-authenticate at: https://developers.tiktok.com/apps/")
            return False

        if resp.status_code != 200:
            print(f"[TIKTOK] Init failed ({resp.status_code}): {resp_data}")
            return False

        upload_url = resp_data["data"]["upload_url"]
        publish_id = resp_data["data"]["publish_id"]

        # Step 2: Upload the video file
        with open(video_path, "rb") as f:
            video_data = f.read()

        upload_headers = {
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        }
        upload_resp = requests.put(upload_url, headers=upload_headers, data=video_data, timeout=120)

        if upload_resp.status_code not in (200, 201):
            print(f"[TIKTOK] Upload failed ({upload_resp.status_code}): {upload_resp.text}")
            return False

        print(f"[TIKTOK] Upload successful! Publish ID: {publish_id}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"[TIKTOK] Network error: {e}")
        return False


def upload_instagram(video_path: Path, caption: str) -> bool:
    """
    Upload a Reel to Instagram via instagrapi.
    Requires INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in .env.
    """
    username = os.getenv("INSTAGRAM_USERNAME")
    password = os.getenv("INSTAGRAM_PASSWORD")
    if not username or not password or username.startswith("your_"):
        print("[INSTAGRAM] Skipped — INSTAGRAM_USERNAME/PASSWORD not configured in .env")
        return False

    try:
        from instagrapi import Client

        cl = Client()
        cl.login(username, password)

        media = cl.clip_upload(str(video_path), caption)
        print(f"[INSTAGRAM] Reel uploaded! Media ID: {media.pk}")
        return True

    except ImportError:
        print("[INSTAGRAM] Error: 'instagrapi' not installed. Run: pip install instagrapi")
        return False
    except Exception as e:
        err = str(e).lower()
        if "login_required" in err or "challenge" in err or "checkpoint" in err:
            print(f"[INSTAGRAM] Auth error: {e}")
            print("[INSTAGRAM] Re-authenticate: log into Instagram manually, then retry.")
        else:
            print(f"[INSTAGRAM] Upload failed: {e}")
        return False


def distribute(video_path: Path, caption: str) -> bool:
    """Attempt uploads to configured platforms. Returns True if any succeeded."""
    results = {}

    results["tiktok"] = upload_tiktok(video_path, caption)
    results["instagram"] = upload_instagram(video_path, caption)

    print(f"\n[DISTRIBUTE] Results: {results}")

    if not any(results.values()):
        print("[DISTRIBUTE] WARNING: No uploads succeeded. Check your .env credentials.")
        return False

    return True


# ── 3. Archive & Cleanup ─────────────────────────────────────────────────────

def archive_video(video_path: Path) -> Path:
    """Move the exported MP4 to permanent_archive/ labeled by date."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    dest_dir = ARCHIVE_DIR / date_str
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / video_path.name
    shutil.move(str(video_path), str(dest_path))
    print(f"[ARCHIVE] Moved {video_path.name} → {dest_path}")
    return dest_path


def cleanup_temp():
    """Wipe temp/ frames and audio files (mirrors CleanupManager from Phase 2)."""
    if TEMP_DIR.is_dir():
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        print(f"[CLEANUP] Removed {TEMP_DIR}/")
    else:
        print(f"[CLEANUP] {TEMP_DIR}/ already clean.")


def _append_handover(content: str):
    """Append a section to HANDOVER.md."""
    with open(HANDOVER_MD, "a") as f:
        f.write("\n" + content)


def finalize_handover(archive_path: Path):
    """Update HANDOVER.md with completed status."""
    timestamp = datetime.now().isoformat()
    section = (
        f"\n---\n\n"
        f"## Project Lifecycle: Completed\n\n"
        f"- **Completed at**: {timestamp}\n"
        f"- **Archived video**: `{archive_path.relative_to(PROJECT_ROOT)}`\n"
        f"- **Status**: Distribution complete. Temp files cleaned.\n"
    )
    _append_handover(section)
    print(f"[HANDOVER] Updated with completion status.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  WORD OF THE DAY PIPELINE — Phase 3: Distribute")
    print("=" * 60)

    # Step 1: Approval Gate
    video_path = approval_gate()

    # Step 2: Build caption from data_bridge.json
    data = load_data_bridge()
    caption = build_caption(data)
    print(f"[Phase 3] Caption: {caption}")

    # Step 3: Distribute to social platforms
    success = distribute(video_path, caption)

    if not success:
        print("\n[Phase 3] No uploads succeeded. Video remains in exports/.")
        print("[Phase 3] Fix credentials in .env and re-run: python approve.py")
        sys.exit(1)

    # Step 4: Archive & Cleanup
    archive_path = archive_video(video_path)
    cleanup_temp()
    finalize_handover(archive_path)

    print("\n" + "=" * 60)
    print("  PHASE 3 COMPLETE — Video distributed & archived.")
    print(f"  Archive: {archive_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
