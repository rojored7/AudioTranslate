#!/usr/bin/env python3
"""
sync_to_github.py — Sube libros de AudioTranslate a GitHub Releases.

Uso:
    python scripts/sync_to_github.py                 # sincronizar todos los libros
    python scripts/sync_to_github.py --book-id 3    # solo un libro
    python scripts/sync_to_github.py --dry-run      # listar sin subir

Requiere en .env (raiz del proyecto) o variables de entorno:
    GITHUB_TOKEN=ghp_...     (PAT con scope 'repo')
    GITHUB_REPO=owner/repo   (repositorio de destino)
"""

import argparse
import io
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' no está instalado. Ejecuta: pip install requests")
    sys.exit(1)

# ── Cargar .env ────────────────────────────────────────────────────────────────

_root = Path(__file__).parent.parent
_env_file = _root / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        # Fallback: parseo manual si python-dotenv no está instalado
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

# ── Config ─────────────────────────────────────────────────────────────────────

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "")
LOCAL_API    = os.environ.get("LOCAL_API_URL", "http://localhost:9001")
GITHUB_API   = "https://api.github.com"

_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _check_config():
    errors = []
    if not GITHUB_TOKEN:
        errors.append("GITHUB_TOKEN no configurado. Crea un .env con GITHUB_TOKEN=ghp_...")
    if not GITHUB_REPO:
        errors.append("GITHUB_REPO no configurado. Crea un .env con GITHUB_REPO=owner/repo")
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        sys.exit(1)


# ── API helpers ────────────────────────────────────────────────────────────────

def list_books() -> list[dict]:
    resp = requests.get(f"{LOCAL_API}/books/", timeout=10)
    resp.raise_for_status()
    return resp.json().get("books", [])


def export_book_zip(book_id: int) -> tuple[bytes, str]:
    resp = requests.get(f"{LOCAL_API}/books/{book_id}/export", stream=True, timeout=120)
    resp.raise_for_status()
    buf = io.BytesIO()
    for chunk in resp.iter_content(chunk_size=8192):
        buf.write(chunk)
    cd = resp.headers.get("Content-Disposition", "")
    filename = ""
    if "filename=" in cd:
        filename = cd.split("filename=")[-1].strip().strip('"')
    if not filename:
        filename = f"audiobook_book{book_id}.zip"
    return buf.getvalue(), filename


def get_or_create_release(book_id: int, title: str) -> dict:
    tag = f"book-{book_id}"
    resp = requests.get(
        f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/tags/{tag}",
        headers=_HEADERS, timeout=15,
    )
    if resp.status_code == 200:
        return resp.json()
    payload = {
        "tag_name": tag,
        "name": title,
        "body": f"AudioTranslate export — libro ID {book_id}",
        "draft": False,
        "prerelease": False,
    }
    resp = requests.post(
        f"{GITHUB_API}/repos/{GITHUB_REPO}/releases",
        headers=_HEADERS, json=payload, timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def upload_asset(release: dict, zip_bytes: bytes, filename: str) -> dict:
    for asset in release.get("assets", []):
        if asset["name"] == filename:
            requests.delete(
                f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/assets/{asset['id']}",
                headers=_HEADERS, timeout=15,
            )
            break
    upload_url = release["upload_url"].split("{")[0] + f"?name={filename}"
    upload_headers = {**_HEADERS, "Content-Type": "application/zip"}
    resp = requests.post(upload_url, headers=upload_headers, data=zip_bytes, timeout=300)
    resp.raise_for_status()
    return resp.json()


# ── Core sync ──────────────────────────────────────────────────────────────────

def sync_book(book_id: int, title: str, dry_run: bool = False) -> bool:
    print(f"  → Exportando libro {book_id}: '{title}'...")
    if dry_run:
        print("    [dry-run] Se saltaría la subida a GitHub.")
        return True
    try:
        zip_bytes, filename = export_book_zip(book_id)
        size_mb = len(zip_bytes) / (1024 * 1024)
        print(f"    ZIP: {filename} ({size_mb:.1f} MB)")
        release = get_or_create_release(book_id, title)
        asset = upload_asset(release, zip_bytes, filename)
        print(f"    ✓ Publicado: {asset['browser_download_url']}")
        return True
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False


def main():
    _check_config()

    parser = argparse.ArgumentParser(description="Sube libros de AudioTranslate a GitHub Releases")
    parser.add_argument("--book-id", type=int, metavar="ID",
                        help="ID del libro a sincronizar (omitir = todos los libros)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Listar libros y ZIPs sin subir a GitHub")
    args = parser.parse_args()

    print(f"[sync] Conectando a {LOCAL_API}...")
    try:
        books = list_books()
    except Exception as e:
        print(f"ERROR: No se pudo conectar a {LOCAL_API}: {e}")
        print("       ¿Está corriendo el servidor de AudioTranslate?")
        sys.exit(1)

    if not books:
        print("[sync] No hay libros en la biblioteca.")
        return

    if args.book_id is not None:
        books = [b for b in books if b["id"] == args.book_id]
        if not books:
            print(f"ERROR: No se encontró libro con ID {args.book_id}")
            sys.exit(1)

    print(f"[sync] {len(books)} libro(s) → {GITHUB_REPO}")
    ok = fail = 0
    for book in books:
        success = sync_book(book["id"], book["title"], dry_run=args.dry_run)
        if success:
            ok += 1
        else:
            fail += 1

    print(f"\n[sync] Completado: {ok} ✓  {fail} ✗")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
