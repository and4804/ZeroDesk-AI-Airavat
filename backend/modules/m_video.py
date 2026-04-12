"""
M-Video — Video Recording Storage, Keyword Clip Extraction & SHA-256 Integrity

Flow
────
1. Frontend sends full session WebM blob via POST /api/video/{session_id}/upload
2. Backend saves raw video, computes SHA-256, stores metadata in DB
3. POST /api/video/{session_id}/extract reads Whisper word_timestamps from the
   session store and uses ffmpeg to cut clips around loan-related keywords
4. Each clip gets its own SHA-256 hash; all metadata is stored in video_recordings
5. GET /api/video/{session_id} returns recording metadata + clip list
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/video", tags=["M-Video"])

# ─────────────────────────────────────────────────────────────────
# Storage directory  (sibling to the SQLite DB)
# ─────────────────────────────────────────────────────────────────
_VIDEO_DIR = Path(settings.DATABASE_PATH).parent / "videos"
_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# Keywords whose vicinity (±3 s) should be clipped
CLIP_KEYWORDS: frozenset[str] = frozenset({
    "loan", "income", "salary", "amount", "emi", "interest", "rupees",
    "lakh", "consent", "agree", "purpose", "employment", "age",
    "name", "approve", "reject", "offer", "bank",
})

# Clip config
CLIP_PRE_SEC = 3.0   # seconds before keyword
CLIP_POST_SEC = 3.0  # seconds after keyword
MAX_CLIPS = 10       # cap per session


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ffmpeg_clip(src: Path, start: float, duration: float, dst: Path) -> bool:
    """Extract a clip from `src` using ffmpeg. Returns True on success."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(max(start, 0)),
                "-i", str(src),
                "-t", str(duration),
                "-c", "copy",
                str(dst),
            ],
            capture_output=True,
            timeout=60,
        )
        return result.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _find_clip_windows(
    word_timestamps: list[dict],
    keywords: frozenset[str],
    pre: float,
    post: float,
    max_clips: int,
) -> list[tuple[float, float, str]]:
    """
    Return a deduplicated list of (start, end, keyword) clip windows.
    Merges overlapping windows to avoid redundant clips.
    """
    hits: list[tuple[float, float, str]] = []
    for entry in word_timestamps:
        word = entry.get("word", "").lower().strip(".,!? ")
        if word in keywords:
            ws = float(entry.get("start", 0))
            we = float(entry.get("end", ws))
            hits.append((max(0.0, ws - pre), we + post, word))

    if not hits:
        return []

    # Sort and merge overlapping windows
    hits.sort(key=lambda x: x[0])
    merged: list[tuple[float, float, str]] = [hits[0]]
    for start, end, kw in hits[1:]:
        last_start, last_end, last_kw = merged[-1]
        if start <= last_end:  # overlapping
            merged[-1] = (last_start, max(last_end, end), last_kw)
        else:
            merged.append((start, end, kw))
        if len(merged) >= max_clips:
            break

    return merged[:max_clips]


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────

@router.post("/{session_id}/upload")
async def upload_video(session_id: str, file: UploadFile = File(...)):
    """
    Receive the full session WebM recording from the frontend.
    Stores it on disk, computes SHA-256, persists metadata.
    """
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Read upload
    video_bytes = await file.read()
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Empty video upload")

    file_hash = _sha256_bytes(video_bytes)
    ext = Path(file.filename or "recording.webm").suffix or ".webm"
    video_path = _VIDEO_DIR / f"{session_id}{ext}"

    # Write to disk
    with open(video_path, "wb") as fh:
        fh.write(video_bytes)

    size_bytes = len(video_bytes)
    now = datetime.utcnow().isoformat()

    # Persist metadata
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR REPLACE INTO video_recordings
               (session_id, file_path, file_hash, size_bytes, status, created_at)
               VALUES (?, ?, ?, ?, 'uploaded', ?)""",
            (session_id, str(video_path), file_hash, size_bytes, now),
        )
        await db.commit()
    finally:
        await db.close()

    store.update(session_id, {
        "video_path": str(video_path),
        "video_hash": file_hash,
    })

    await audit.emit(session_id, "VIDEO_UPLOADED", "VIDEO", {
        "size_bytes": size_bytes,
        "sha256": file_hash[:16] + "...",
    })

    return {
        "session_id": session_id,
        "file_path": str(video_path),
        "sha256": file_hash,
        "size_bytes": size_bytes,
        "status": "uploaded",
    }


@router.post("/{session_id}/extract")
async def extract_clips(session_id: str):
    """
    Extract keyword clips from the uploaded session video using ffmpeg.
    Uses Whisper word_timestamps stored in the session transcript.
    """
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    video_path_str: Optional[str] = session.get("video_path")
    if not video_path_str or not Path(video_path_str).exists():
        raise HTTPException(status_code=404, detail="No video found for this session — upload first")

    video_path = Path(video_path_str)

    # Collect word timestamps from all transcript segments
    all_words: list[dict] = []
    for seg in session.get("transcript", []):
        wts = seg.get("word_timestamps", [])
        if isinstance(wts, list):
            all_words.extend(wts)

    if not all_words:
        return {
            "session_id": session_id,
            "message": "No word timestamps available — Whisper word_timestamps require real audio",
            "clips": [],
        }

    windows = _find_clip_windows(all_words, CLIP_KEYWORDS, CLIP_PRE_SEC, CLIP_POST_SEC, MAX_CLIPS)

    if not windows:
        return {"session_id": session_id, "message": "No keyword matches found", "clips": []}

    clips_dir = _VIDEO_DIR / session_id
    clips_dir.mkdir(exist_ok=True)

    clips_meta: list[dict] = []
    ffmpeg_ok = _ffmpeg_available()

    for i, (start, end, keyword) in enumerate(windows):
        duration = round(end - start, 3)
        clip_name = f"clip_{i:02d}_{keyword}_{int(start)}s.webm"
        clip_path = clips_dir / clip_name
        clip_hash: Optional[str] = None
        clip_size = 0
        success = False

        if ffmpeg_ok:
            success = _ffmpeg_clip(video_path, start, duration, clip_path)
            if success:
                clip_hash = _sha256_file(clip_path)
                clip_size = clip_path.stat().st_size
        else:
            # ffmpeg not available — record metadata anyway (no actual clip)
            success = False
            clip_hash = None

        clips_meta.append({
            "index": i,
            "keyword": keyword,
            "start_sec": start,
            "end_sec": end,
            "duration_sec": duration,
            "clip_path": str(clip_path) if success else None,
            "sha256": clip_hash,
            "size_bytes": clip_size,
            "extracted": success,
        })

    # Persist clips to DB
    db = await get_db()
    try:
        await db.execute(
            """UPDATE video_recordings
               SET clips_json = ?, status = 'clips_extracted', updated_at = ?
               WHERE session_id = ?""",
            (json.dumps(clips_meta), datetime.utcnow().isoformat(), session_id),
        )
        await db.commit()
    finally:
        await db.close()

    await audit.emit(session_id, "VIDEO_CLIPS_EXTRACTED", "VIDEO", {
        "clip_count": len(clips_meta),
        "ffmpeg_available": ffmpeg_ok,
        "keywords_found": list({c["keyword"] for c in clips_meta}),
    })

    return {
        "session_id": session_id,
        "clip_count": len(clips_meta),
        "ffmpeg_available": ffmpeg_ok,
        "clips": clips_meta,
    }


@router.get("/{session_id}")
async def get_video_info(session_id: str):
    """Return video recording metadata and clip list for a session."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM video_recordings WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No video recording found")
        data = dict(row)
        if data.get("clips_json"):
            data["clips"] = json.loads(data.pop("clips_json"))
        return data
    finally:
        await db.close()
