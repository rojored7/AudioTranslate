# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup & run (Windows, creates venv automatically)
run.bat

# Manual setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -c "from db import init_db; init_db()"
python main.py          # server starts on port 9001

# Health check
curl http://localhost:9001/health

# Reset database
del data\audiobookplayer.db && python main.py
```

There is no test suite yet.

## Architecture

Single-process FastAPI app that runs entirely locally. No auth, no external services required (except for the optional TTS engines).

### Request flow

```
Browser → FastAPI (main.py)
             ├── routers/books.py     → book_parser.py → db.py
             ├── routers/audio.py     → tts_engine.py  → db.py
             ├── routers/progress.py  → db.py
             ├── routers/settings.py  → tts_engine.py  → db.py
             └── routers/export.py    → db.py
```

### Key modules

| File | Role |
|------|------|
| `main.py` | FastAPI app bootstrap, static file serving, router mounting |
| `db.py` | All SQLite access — raw `sqlite3`, no ORM. Context manager `get_db()` wraps every connection. |
| `tts_engine.py` | Abstract `TTSEngine` base class + three concrete engines. Factory `get_tts_engine()` constructs from settings. |
| `book_parser.py` | Text extraction (PDF via pdfplumber, EPUB via ebooklib, TXT) and sentence-boundary segmentation (~500 words/segment). |
| `routers/audio.py` | Serves cached WAV/MP3 files; on-demand and background generation. Background generation uses `threading.Thread`. |
| `routers/export.py` | Packages book text + cached audio into a ZIP for offline transfer. |

### TTS engines

Three engines share the `TTSEngine` ABC (`generate_audio`, `is_available`):

- **Kokoro ONNX** (`kokoro`) — default, ~300 MB model downloaded on first use, CPU-only, English voices (e.g. `af_heart`).
- **Ollama/Orpheus** (`ollama`) — streams SNAC tokens from Ollama's OpenAI-compatible `/v1/completions`, decodes locally with the SNAC model. Requires `ollama` running + `legraphista/Orpheus:latest` pulled. GPU recommended.
- **Edge TTS** (`edge_tts`) — Microsoft neural voices, requires internet, Spanish-optimized, outputs MP3.

The active engine and its voice are persisted in the `settings` SQLite table and read from DB on every request via `get_all_settings()`.

### Data layout

```
data/
├── audiobookplayer.db      # SQLite (books, segments, reading_progress, settings)
├── books/                  # Uploaded source files (PDF/EPUB/TXT)
└── audio_cache/            # Generated audio: {book_id}_{segment_index}.wav|mp3
```

Audio lookup checks both `.wav` and `.mp3` extensions (`_find_audio_file`); the write extension depends on the engine.

### Frontend

Plain HTML + vanilla JS in `static/`. No build step. `index.html` is the library view; `player.html` is the player. `app.js` calls the REST API directly. The root `GET /` serves `index.html` via `FileResponse`.

### Port

The server listens on **9001**, not 8000 (README is outdated — see `main.py:48`).

### Settings keys

Valid keys stored in `settings` table: `tts_engine`, `ollama_url`, `ollama_model`, `kokoro_voice`, `edge_tts_voice`.

## Adding a new TTS engine

1. Subclass `TTSEngine` in `tts_engine.py`, implement `generate_audio` and `is_available`.
2. Add a branch to `get_tts_engine()` factory.
3. Wire it into `routers/audio.py::_get_engine()` and `routers/settings.py`.
4. Add the new key to `valid_keys` in `settings.py` if new settings are needed.
