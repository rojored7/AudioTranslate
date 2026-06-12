"""Tests del progreso de lectura y su reset (db.py + routers/progress.py)."""
import asyncio

import pytest
from fastapi import HTTPException

import db
from routers.progress import reset_progress


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Base de datos SQLite temporal y aislada por test."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return db


def _make_book(database) -> int:
    return database.add_book(
        title="Libro de prueba",
        author="Autor",
        file_path="/tmp/libro.txt",
        format="txt",
        total_segments=10,
    )


def test_progress_roundtrip_set_then_get(temp_db):
    # Arrange
    book_id = _make_book(temp_db)

    # Act
    temp_db.set_reading_progress(book_id, 5)

    # Assert
    assert temp_db.get_reading_progress(book_id) == 5


def test_progress_defaults_to_zero_without_rows(temp_db):
    book_id = _make_book(temp_db)
    assert temp_db.get_reading_progress(book_id) == 0


def test_reset_endpoint_sets_progress_to_zero(temp_db):
    # Arrange: libro avanzado hasta el segmento 5
    book_id = _make_book(temp_db)
    temp_db.set_reading_progress(book_id, 5)

    # Act
    response = asyncio.run(reset_progress(book_id))

    # Assert: respuesta y estado persistido vuelven a 0
    assert response == {"success": True, "book_id": book_id, "current_segment": 0}
    assert temp_db.get_reading_progress(book_id) == 0


def test_reset_endpoint_returns_404_for_missing_book(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(reset_progress(99999))
    assert exc_info.value.status_code == 404
