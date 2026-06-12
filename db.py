import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "audiobookplayer.db"

def init_db():
    """Initialize SQLite database with schema."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                file_path TEXT NOT NULL,
                format TEXT,
                total_segments INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                segment_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                audio_path TEXT,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reading_progress (
                book_id INTEGER PRIMARY KEY,
                current_segment INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Initialize default settings
        defaults = [
            ('tts_engine', 'ollama'),
            ('ollama_url', 'http://localhost:11434'),
            ('ollama_model', 'legraphista/Orpheus:latest'),
            ('kokoro_voice', 'af_heart'),
        ]

        for key, value in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )

        conn.commit()

@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def add_book(title: str, author: str, file_path: str, format: str, total_segments: int) -> int:
    """Add a book to the database. Returns book_id."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO books (title, author, file_path, format, total_segments)
               VALUES (?, ?, ?, ?, ?)""",
            (title, author, file_path, format, total_segments)
        )
        conn.commit()
        return cursor.lastrowid

def add_segments(book_id: int, segments: list[dict]):
    """Add segments for a book. Each segment: {segment_index, text}"""
    with get_db() as conn:
        for seg in segments:
            conn.execute(
                """INSERT INTO segments (book_id, segment_index, text, audio_path)
                   VALUES (?, ?, ?, NULL)""",
                (book_id, seg['segment_index'], seg['text'])
            )
        conn.commit()

def get_book(book_id: int) -> dict:
    """Get book metadata."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return dict(row) if row else None

def get_all_books() -> list[dict]:
    """Get all books with progress."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM books ORDER BY created_at DESC").fetchall()
        books = [dict(row) for row in rows]

        # Add progress and audio count for each book
        for book in books:
            progress = conn.execute(
                "SELECT current_segment FROM reading_progress WHERE book_id = ?",
                (book['id'],)
            ).fetchone()
            book['current_segment'] = progress['current_segment'] if progress else 0

            audio_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM segments WHERE book_id = ? AND audio_path IS NOT NULL",
                (book['id'],)
            ).fetchone()
            book['audio_cached'] = audio_row['cnt'] if audio_row else 0

        return books

def get_segments(book_id: int) -> list[dict]:
    """Get all segments for a book."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM segments WHERE book_id = ? ORDER BY segment_index",
            (book_id,)
        ).fetchall()
        return [dict(row) for row in rows]

def get_segment(book_id: int, segment_index: int) -> dict:
    """Get a specific segment."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM segments WHERE book_id = ? AND segment_index = ?",
            (book_id, segment_index)
        ).fetchone()
        return dict(row) if row else None

def update_segment_audio_path(book_id: int, segment_index: int, audio_path: str):
    """Update the audio_path for a segment after generation."""
    with get_db() as conn:
        conn.execute(
            "UPDATE segments SET audio_path = ? WHERE book_id = ? AND segment_index = ?",
            (audio_path, book_id, segment_index)
        )
        conn.commit()

def get_reading_progress(book_id: int) -> int:
    """Get current segment index for a book."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT current_segment FROM reading_progress WHERE book_id = ?",
            (book_id,)
        ).fetchone()
        return row['current_segment'] if row else 0

def set_reading_progress(book_id: int, current_segment: int):
    """Update reading progress for a book."""
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO reading_progress (book_id, current_segment, updated_at)
               VALUES (?, ?, ?)""",
            (book_id, current_segment, datetime.now().isoformat())
        )
        conn.commit()

def delete_book(book_id: int):
    """Delete a book and all its segments and progress."""
    with get_db() as conn:
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.execute("DELETE FROM segments WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM reading_progress WHERE book_id = ?", (book_id,))
        conn.commit()

def get_setting(key: str) -> str:
    """Get a setting value."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else None

def set_setting(key: str, value: str):
    """Set a setting value."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()

def get_all_settings() -> dict:
    """Get all settings as a dictionary."""
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row['key']: row['value'] for row in rows}
