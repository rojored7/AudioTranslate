import os
import subprocess
import sys
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from db import get_segment, get_book, update_segment_audio_path, get_all_settings, get_segments
from tts_engine import get_tts_engine

router = APIRouter(prefix="/audio", tags=["audio"])

AUDIO_CACHE_DIR = Path(__file__).parent.parent / "data" / "audio_cache"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

MIME_BY_EXT = {".wav": "audio/wav", ".mp3": "audio/mpeg"}


def _find_audio_file(book_id: int, segment_index: int) -> Path | None:
    """Find existing audio file for a segment (supports .wav and .mp3)."""
    for ext in (".wav", ".mp3"):
        p = AUDIO_CACHE_DIR / f"{book_id}_{segment_index}{ext}"
        if p.exists():
            return p
    return None


def _get_output_path(book_id: int, segment_index: int, engine_type: str) -> Path:
    """Return write path with correct extension for the engine."""
    ext = ".mp3" if engine_type == "edge_tts" else ".wav"
    return AUDIO_CACHE_DIR / f"{book_id}_{segment_index}{ext}"


def _get_engine():
    settings = get_all_settings()
    engine_type = settings.get("tts_engine", "ollama")
    if engine_type == "ollama":
        return get_tts_engine(
            "ollama",
            ollama_url=settings.get("ollama_url", "http://localhost:11434"),
            model=settings.get("ollama_model", "legraphista/Orpheus:latest"),
        ), "ollama"
    elif engine_type == "edge_tts":
        return get_tts_engine(
            "edge_tts",
            voice=settings.get("edge_tts_voice", "es-ES-AlvaroNeural"),
        ), "edge_tts"
    else:
        return get_tts_engine("kokoro", voice=settings.get("kokoro_voice", "af_heart")), "kokoro"


def _generate_audio_file(book_id: int, segment_index: int, text: str) -> bool:
    try:
        engine, engine_type = _get_engine()
        if not engine.is_available():
            print(f"[audio] TTS engine not available, skipping segment {segment_index}")
            return False
        output_path = _get_output_path(book_id, segment_index, engine_type)
        success = engine.generate_audio(text, str(output_path))
        if success:
            update_segment_audio_path(book_id, segment_index, str(output_path))
        return success
    except Exception as e:
        print(f"[audio] Error generating segment {segment_index}: {e}")
        return False


def _trigger_github_sync(book_id: int) -> None:
    if not (os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPO")):
        return
    script = Path(__file__).parent.parent / "scripts" / "sync_to_github.py"
    if not script.exists():
        return
    try:
        subprocess.Popen(
            [sys.executable, str(script), "--book-id", str(book_id)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[audio] GitHub sync iniciado para book_id={book_id}")
    except Exception as e:
        print(f"[audio] No se pudo iniciar GitHub sync: {e}")


def _generate_all_segments(book_id: int):
    try:
        segments = get_segments(book_id)
        for seg in segments:
            if not _find_audio_file(book_id, seg["segment_index"]):
                _generate_audio_file(book_id, seg["segment_index"], seg["text"])
        _trigger_github_sync(book_id)
    except Exception as e:
        print(f"[audio] Background generation error: {e}")


# ── Specific routes BEFORE parameterized routes ──────────────────────────────

@router.get("/{book_id}/progress")
async def get_book_audio_progress(book_id: int):
    """Count segments with actual audio files on disk (not stale DB data)."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    segments = get_segments(book_id)
    cached = 0
    for seg in segments:
        audio_file = _find_audio_file(book_id, seg["segment_index"])
        if audio_file:
            cached += 1
        elif seg.get("audio_path"):
            update_segment_audio_path(book_id, seg["segment_index"], None)

    return {"cached": cached, "total": len(segments)}


@router.post("/{book_id}/generate-all")
async def generate_all_audio(book_id: int):
    """Start background audio generation for all un-cached segments."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    engine, _ = _get_engine()
    if not engine.is_available():
        raise HTTPException(status_code=503, detail="TTS engine not available")

    import threading
    threading.Thread(target=_generate_all_segments, args=(book_id,), daemon=True).start()

    return {"success": True, "message": "Audio generation started"}


# ── Parameterized routes ──────────────────────────────────────────────────────

@router.get("/{book_id}/{segment_index}/status")
async def get_audio_status(book_id: int, segment_index: int):
    """Check if audio file exists on disk for a segment."""
    segment = get_segment(book_id, segment_index)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    audio_file = _find_audio_file(book_id, segment_index)
    if not audio_file and segment.get("audio_path"):
        update_segment_audio_path(book_id, segment_index, None)
    return {"cached": audio_file is not None}


@router.get("/{book_id}/{segment_index}")
async def get_audio(book_id: int, segment_index: int):
    """Serve a cached audio file. Returns 404 if not yet generated."""
    segment = get_segment(book_id, segment_index)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    audio_file = _find_audio_file(book_id, segment_index)
    if not audio_file:
        raise HTTPException(status_code=404, detail="Audio not generated yet.")

    media_type = MIME_BY_EXT.get(audio_file.suffix, "audio/wav")
    return FileResponse(
        path=audio_file,
        media_type=media_type,
        filename=f"segment_{segment_index}{audio_file.suffix}",
    )
