import io
import json
import zipfile
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pathlib import Path
from db import get_book, get_segments

router = APIRouter(prefix="/books", tags=["export"])

AUDIO_CACHE_DIR = Path(__file__).parent.parent / "data" / "audio_cache"


def _find_audio_file(book_id: int, segment_index: int) -> Path | None:
    for ext in (".wav", ".mp3"):
        p = AUDIO_CACHE_DIR / f"{book_id}_{segment_index}{ext}"
        if p.exists():
            return p
    return None


@router.get("/{book_id}/export")
def export_book(book_id: int):
    """Export a book and its cached audio files as a ZIP for transfer to PC B."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    segments = get_segments(book_id)

    seg_meta = []
    for seg in segments:
        entry = {"segment_index": seg["segment_index"], "text": seg["text"]}
        audio_file = _find_audio_file(book_id, seg["segment_index"])
        if audio_file:
            entry["audio_file"] = f"audio/{seg['segment_index']}{audio_file.suffix}"
        seg_meta.append(entry)

    metadata = {
        "title": book["title"],
        "author": book["author"] or "",
        "format": book["format"],
        "total_segments": book["total_segments"],
        "segments": seg_meta,
    }

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        for seg in segments:
            audio_file = _find_audio_file(book_id, seg["segment_index"])
            if audio_file:
                zf.write(str(audio_file), f"audio/{seg['segment_index']}{audio_file.suffix}")

    zip_buffer.seek(0)
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in book["title"])[:50].strip()
    filename = f"audiobook_{safe_title}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
