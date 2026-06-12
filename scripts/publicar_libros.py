#!/usr/bin/env python3
"""publicar_libros.py — Publica la biblioteca para el reproductor web (PC B).

Empaqueta cada libro de la DB local (texto + audio generado) en un ZIP y
publica todo en la rama 'libros' del repo, junto a un index.json. El
reproductor web (reproductor.html) descarga de ahí vía
raw.githubusercontent.com, que sí permite CORS (los assets de GitHub
Releases NO se pueden descargar desde JavaScript del navegador).

La rama 'libros' es un espejo de la biblioteca local: cada publicación la
reescribe entera con un único commit (force push), así el repo no acumula
historial con archivos de audio pesados.

Uso:
    python scripts/publicar_libros.py            # publica todos los libros
    python scripts/publicar_libros.py --dry-run  # muestra qué subiría

No necesita token: usa la misma credencial de git con la que haces push.
"""

import argparse
import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "audiobookplayer.db"
AUDIO_DIR = ROOT / "data" / "audio_cache"
BRANCH = "libros"
MAX_ZIP_MB = 95  # GitHub rechaza archivos de más de 100 MB en el repo

# Fecha fija en las entradas del ZIP para que el mismo contenido produzca
# siempre los mismos bytes (y el mismo sha256): así el reproductor no
# re-descarga libros que no cambiaron.
FIXED_DATE = (2020, 1, 1, 0, 0, 0)


def find_audio(book_id: int, idx: int) -> Path | None:
    for ext in (".wav", ".mp3"):
        p = AUDIO_DIR / f"{book_id}_{idx}{ext}"
        if p.exists():
            return p
    return None


def build_zip(conn: sqlite3.Connection, book: sqlite3.Row) -> tuple[bytes, int]:
    """Mismo formato que routers/export.py: metadata.json + audio/N.ext."""
    segments = conn.execute(
        "SELECT * FROM segments WHERE book_id = ? ORDER BY segment_index", (book["id"],)
    ).fetchall()

    seg_meta = []
    for seg in segments:
        entry = {"segment_index": seg["segment_index"], "text": seg["text"]}
        audio = find_audio(book["id"], seg["segment_index"])
        if audio:
            entry["audio_file"] = f"audio/{seg['segment_index']}{audio.suffix}"
        seg_meta.append(entry)

    metadata = {
        "title": book["title"],
        "author": book["author"] or "",
        "format": book["format"],
        "total_segments": book["total_segments"],
        "segments": seg_meta,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("metadata.json", date_time=FIXED_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, json.dumps(metadata, ensure_ascii=False, indent=2))
        for seg in segments:
            audio = find_audio(book["id"], seg["segment_index"])
            if audio:
                info = zipfile.ZipInfo(
                    f"audio/{seg['segment_index']}{audio.suffix}", date_time=FIXED_DATE
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, audio.read_bytes())
    with_audio = sum(1 for s in seg_meta if "audio_file" in s)
    return buf.getvalue(), with_audio


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd or ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.exit(f"ERROR git {' '.join(args)}:\n{result.stderr.strip()}")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica la biblioteca en la rama 'libros'")
    parser.add_argument("--dry-run", action="store_true", help="mostrar sin publicar")
    args = parser.parse_args()

    if not DB_PATH.exists():
        sys.exit(f"ERROR: no existe {DB_PATH}. ¿Este es el equipo principal?")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    books = conn.execute("SELECT * FROM books ORDER BY id").fetchall()
    if not books:
        sys.exit("No hay libros en la biblioteca local.")

    print(f"[publicar] {len(books)} libro(s) en la biblioteca local")
    zips: list[tuple[str, bytes]] = []
    index: list[dict] = []
    for book in books:
        zip_bytes, with_audio = build_zip(conn, book)
        size_mb = len(zip_bytes) / 1048576
        filename = f"book-{book['id']}.zip"
        print(f"  - {filename}: '{book['title']}' "
              f"({size_mb:.1f} MB, {with_audio}/{book['total_segments']} con audio)")
        if size_mb > MAX_ZIP_MB:
            print(f"    OMITIDO: supera {MAX_ZIP_MB} MB (limite de GitHub)")
            continue
        zips.append((filename, zip_bytes))
        index.append({
            "id": book["id"],
            "title": book["title"],
            "author": book["author"] or "",
            "format": book["format"],
            "total_segments": book["total_segments"],
            "audio_segments": with_audio,
            "file": filename,
            "size": len(zip_bytes),
            "sha256": hashlib.sha256(zip_bytes).hexdigest(),
        })

    if not zips:
        sys.exit("Nada que publicar.")
    if args.dry_run:
        print("[dry-run] No se publica nada.")
        return

    remote = git("remote", "get-url", "origin")
    index_doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "books": index,
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "index.json").write_text(
            json.dumps(index_doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for filename, data in zips:
            (tmp_path / filename).write_bytes(data)
        git("init", "-q", "-b", BRANCH, cwd=tmp_path)
        git("add", "-A", cwd=tmp_path)
        git("-c", "user.name=publicar_libros", "-c", "user.email=publicar@local",
            "commit", "-q", "-m", f"biblioteca: {len(zips)} libro(s)", cwd=tmp_path)
        print(f"[publicar] Subiendo a la rama '{BRANCH}' (puede tardar)...")
        git("push", "--force", remote, f"HEAD:refs/heads/{BRANCH}", cwd=tmp_path)

    print(f"[publicar] OK: {len(zips)} libro(s) publicados en {remote} rama '{BRANCH}'")


if __name__ == "__main__":
    main()
