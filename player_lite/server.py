#!/usr/bin/env python3
"""
AudioBook Lite — PC B player.
Python stdlib only. No pip install required.
"""

import http.server
import io
import json
import mimetypes
import os
import sqlite3
import threading
import time
import urllib.request
import urllib.error
import webbrowser
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR   = BASE_DIR / "data"
AUDIO_DIR  = DATA_DIR / "audio_cache"
DB_PATH    = DATA_DIR / "player_lite.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

PORT = 9002

# ── GitHub Sync Config ────────────────────────────────────────────────────────

GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO     = os.environ.get("GITHUB_REPO", "")      # "owner/repo"
SYNC_INTERVAL   = int(os.environ.get("SYNC_INTERVAL_MINUTES", "5")) * 60  # seconds
# Token opcional: un repo PUBLICO se sincroniza sin token (solo el repo).
SYNC_ENABLED    = bool(GITHUB_REPO)
GITHUB_API_BASE = "https://api.github.com"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css",
    ".js":   "application/javascript",
    ".mp3":  "audio/mpeg",
    ".wav":  "audio/wav",
    ".json": "application/json",
}

# ── Database ──────────────────────────────────────────────────────────────────

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT,
            format TEXT,
            total_segments INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            segment_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            audio_path TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS reading_progress (
            book_id INTEGER PRIMARY KEY,
            current_segment INTEGER DEFAULT 0
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS github_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            github_asset_id INTEGER NOT NULL UNIQUE,
            github_tag TEXT NOT NULL,
            asset_name TEXT NOT NULL,
            book_id INTEGER,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        conn.commit()


def _find_audio(book_id, segment_index):
    for ext in (".mp3", ".wav"):
        p = AUDIO_DIR / f"{book_id}_{segment_index}{ext}"
        if p.exists():
            return p
    return None


def db_get_all_books():
    with _connect() as conn:
        books = [dict(r) for r in conn.execute(
            "SELECT * FROM books ORDER BY created_at DESC"
        ).fetchall()]
        for book in books:
            row = conn.execute(
                "SELECT current_segment FROM reading_progress WHERE book_id = ?",
                (book["id"],)
            ).fetchone()
            book["current_segment"] = row["current_segment"] if row else 0
            book["audio_cached"] = sum(
                1 for i in range(book["total_segments"])
                if _find_audio(book["id"], i)
            )
        return books


def db_get_book(book_id):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return dict(row) if row else None


def db_get_segments(book_id):
    with _connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM segments WHERE book_id = ? ORDER BY segment_index",
            (book_id,)
        ).fetchall()]


def db_get_progress(book_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT current_segment FROM reading_progress WHERE book_id = ?",
            (book_id,)
        ).fetchone()
        return row["current_segment"] if row else 0


def db_set_progress(book_id, segment):
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reading_progress (book_id, current_segment) VALUES (?, ?)",
            (book_id, segment)
        )
        conn.commit()


def db_import_zip(zip_bytes: bytes) -> dict:
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    meta = json.loads(zf.read("metadata.json"))

    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO books (title, author, format, total_segments) VALUES (?, ?, ?, ?)",
            (meta["title"], meta.get("author", ""), meta.get("format", "zip"), meta["total_segments"])
        )
        book_id = cur.lastrowid

        names = zf.namelist()
        for seg in meta["segments"]:
            audio_path = None
            if "audio_file" in seg:
                src = seg["audio_file"]
                ext = Path(src).suffix
                dest = AUDIO_DIR / f"{book_id}_{seg['segment_index']}{ext}"
                if src in names:
                    dest.write_bytes(zf.read(src))
                    audio_path = str(dest)
            conn.execute(
                "INSERT INTO segments (book_id, segment_index, text, audio_path) VALUES (?, ?, ?, ?)",
                (book_id, seg["segment_index"], seg["text"], audio_path)
            )
        conn.commit()

    return {"book_id": book_id, "title": meta["title"], "total_segments": meta["total_segments"]}


def db_asset_already_imported(asset_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM github_sync_log WHERE github_asset_id = ?", (asset_id,)
        ).fetchone()
        return row is not None


def db_record_import(asset_id: int, tag: str, asset_name: str, book_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO github_sync_log "
            "(github_asset_id, github_tag, asset_name, book_id) VALUES (?, ?, ?, ?)",
            (asset_id, tag, asset_name, book_id)
        )
        conn.commit()


def db_get_sync_state() -> dict:
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM sync_state").fetchall()
        return {r["key"]: r["value"] for r in rows}


def db_set_sync_state(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)", (key, value)
        )
        conn.commit()


# ── GitHub API Helpers (stdlib only) ──────────────────────────────────────────

def _gh_request(method: str, path: str, body: bytes | None = None):
    url = f"{GITHUB_API_BASE}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AudioTranslate-Lite/1.0",
    }
    if GITHUB_TOKEN:  # repos publicos funcionan sin token
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _gh_download(url: str) -> bytes:
    headers = {
        "Accept": "application/octet-stream",
        "User-Agent": "AudioTranslate-Lite/1.0",
    }
    if GITHUB_TOKEN:  # repos publicos funcionan sin token
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


# ── GitHub Sync Logic ─────────────────────────────────────────────────────────

def _sync_once() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    db_set_sync_state("last_sync_at", now)
    try:
        releases = _gh_request("GET", f"/repos/{GITHUB_REPO}/releases?per_page=100")
        pending = imported = 0
        for release in releases:
            tag = release.get("tag_name", "")
            if not tag.startswith("book-"):
                continue
            for asset in release.get("assets", []):
                asset_id = asset["id"]
                if db_asset_already_imported(asset_id):
                    continue
                pending += 1
                print(f"[sync] Descargando {asset['name']} (asset {asset_id})...")
                zip_bytes = _gh_download(asset["browser_download_url"])
                info = db_import_zip(zip_bytes)
                db_record_import(asset_id, tag, asset["name"], info["book_id"])
                print(f"[sync] Importado '{info['title']}' como book_id={info['book_id']}")
                imported += 1
        db_set_sync_state("last_error", "")
        return {"ok": True, "pending": pending, "imported": imported}
    except Exception as e:
        err = str(e)
        print(f"[sync] Error: {err}")
        db_set_sync_state("last_error", err)
        return {"ok": False, "error": err}


def _sync_loop():
    time.sleep(10)  # espera que el servidor arranque
    while True:
        nxt = (datetime.now(timezone.utc) + timedelta(seconds=SYNC_INTERVAL)).isoformat()
        db_set_sync_state("next_sync_at", nxt)
        _sync_once()
        nxt = (datetime.now(timezone.utc) + timedelta(seconds=SYNC_INTERVAL)).isoformat()
        db_set_sync_state("next_sync_at", nxt)
        time.sleep(SYNC_INTERVAL)


# ── HTTP Handler ──────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # suppress default request logs

    # ── helpers ──────────────────────────────────────────────────────────────

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_404(self, detail="Not found"):
        self._send_json({"detail": detail}, 404)

    def _send_400(self, detail):
        self._send_json({"detail": detail}, 400)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def _serve_static(self, path: Path):
        if not path.exists() or not path.is_file():
            self._send_404()
            return
        data = path.read_bytes()
        mime = MIME.get(path.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _parse_int(self, value, name="id"):
        try:
            return int(value), None
        except (TypeError, ValueError):
            return None, f"Invalid {name}"

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("", "/"):
            self._serve_static(STATIC_DIR / "index.html")
            return

        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            self._serve_static(STATIC_DIR / rel)
            return

        parts = [p for p in path.split("/") if p]

        # GET /sync/status
        if parts == ["sync", "status"]:
            state = db_get_sync_state()
            self._send_json({
                "enabled": SYNC_ENABLED,
                "last_sync_at": state.get("last_sync_at"),
                "next_sync_at": state.get("next_sync_at"),
                "last_error": state.get("last_error") or None,
                "interval_minutes": SYNC_INTERVAL // 60,
                "github_repo": GITHUB_REPO if SYNC_ENABLED else None,
            })
            return

        # GET /books/
        if parts == ["books"]:
            self._send_json({"books": db_get_all_books()})
            return

        # GET /books/{id}
        if len(parts) == 2 and parts[0] == "books":
            book_id, err = self._parse_int(parts[1])
            if err:
                self._send_400(err)
                return
            book = db_get_book(book_id)
            if not book:
                self._send_404("Book not found")
                return
            segs = db_get_segments(book_id)
            self._send_json({
                "book": book,
                "segments": segs,
                "current_segment": db_get_progress(book_id),
                "total_segments": len(segs),
            })
            return

        # GET /audio/{book_id}/{segment_index}/status
        if len(parts) == 4 and parts[0] == "audio" and parts[3] == "status":
            book_id, _ = self._parse_int(parts[1])
            seg_idx, _ = self._parse_int(parts[2])
            self._send_json({"cached": _find_audio(book_id, seg_idx) is not None})
            return

        # GET /audio/{book_id}/{segment_index}
        if len(parts) == 3 and parts[0] == "audio":
            book_id, _ = self._parse_int(parts[1])
            seg_idx, _ = self._parse_int(parts[2])
            f = _find_audio(book_id, seg_idx)
            if not f:
                self._send_404("Audio not found")
                return
            data = f.read_bytes()
            mime = MIME.get(f.suffix.lower(), "audio/mpeg")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # GET /progress/{book_id}
        if len(parts) == 2 and parts[0] == "progress":
            book_id, _ = self._parse_int(parts[1])
            self._send_json({"current_segment": db_get_progress(book_id)})
            return

        self._send_404()

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        parts = [p for p in path.split("/") if p]

        # POST /books/import
        if parts == ["books", "import"]:
            body = self._read_body()
            try:
                info = db_import_zip(body)
                self._send_json(info, 201)
            except Exception as e:
                self._send_400(str(e))
            return

        # POST /sync/now
        if parts == ["sync", "now"]:
            if not SYNC_ENABLED:
                self._send_json({"error": "Sync no configurado. Agrega GITHUB_REPO al .env (y GITHUB_TOKEN solo si el repo es privado)"}, 503)
                return
            threading.Thread(target=_sync_once, daemon=True).start()
            self._send_json({"ok": True, "message": "Sincronización iniciada"})
            return

        # POST /progress/{book_id}/reset
        if len(parts) == 3 and parts[0] == "progress" and parts[2] == "reset":
            book_id, err = self._parse_int(parts[1])
            if err:
                self._send_400(err)
                return
            if not db_get_book(book_id):
                self._send_404("Book not found")
                return
            db_set_progress(book_id, 0)
            self._send_json({"success": True, "book_id": book_id, "current_segment": 0})
            return

        # POST /progress/{book_id}
        if len(parts) == 2 and parts[0] == "progress":
            book_id, err = self._parse_int(parts[1])
            if err:
                self._send_400(err)
                return
            body = self._read_body()
            try:
                data = json.loads(body) if body else {}
            except (ValueError, json.JSONDecodeError):
                self._send_400("Invalid JSON body")
                return
            db_set_progress(book_id, data.get("segment", 0))
            self._send_json({"ok": True})
            return

        self._send_404()


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()

    if SYNC_ENABLED:
        t = threading.Thread(target=_sync_loop, daemon=True, name="github-sync")
        t.start()
        print(f"[AudioBook Lite] GitHub sync cada {SYNC_INTERVAL // 60}m desde {GITHUB_REPO}")
    else:
        print("[AudioBook Lite] Sync desactivado — agrega GITHUB_REPO al .env para activarlo (GITHUB_TOKEN solo si el repo es privado)")

    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"[AudioBook Lite] Servidor en {url}")
    print("[AudioBook Lite] Ctrl+C para detener")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[AudioBook Lite] Detenido.")
