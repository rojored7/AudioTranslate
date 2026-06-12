from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
from db import add_book, add_segments, get_all_books, get_book, get_segments, delete_book, get_reading_progress

AUDIO_CACHE_DIR = Path(__file__).parent.parent / "data" / "audio_cache"

from book_parser import extract_and_segment, get_book_metadata

router = APIRouter(prefix="/books", tags=["books"])

BOOKS_DIR = Path(__file__).parent.parent / "data" / "books"
BOOKS_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/upload")
async def upload_book(file: UploadFile = File(...)):
    """Upload a book (PDF, EPUB, or TXT)."""
    try:
        # Determine file format
        filename = file.filename.lower()
        if filename.endswith('.pdf'):
            file_format = 'pdf'
        elif filename.endswith('.epub'):
            file_format = 'epub'
        elif filename.endswith('.txt'):
            file_format = 'txt'
        else:
            raise HTTPException(status_code=400, detail="Unsupported format. Use PDF, EPUB, or TXT.")

        # Save file
        file_path = BOOKS_DIR / file.filename
        with open(file_path, 'wb') as f:
            contents = await file.read()
            f.write(contents)

        # Extract text and segment
        text, segments = extract_and_segment(str(file_path), file_format)

        # Get metadata
        metadata = get_book_metadata(str(file_path), file_format)

        # Add book to database
        book_id = add_book(
            title=metadata['title'],
            author=metadata['author'] or "Unknown",
            file_path=str(file_path),
            format=file_format,
            total_segments=len(segments)
        )

        # Add segments
        add_segments(book_id, segments)

        return {
            "success": True,
            "book_id": book_id,
            "title": metadata['title'],
            "total_segments": len(segments),
            "message": f"Book uploaded successfully with {len(segments)} segments"
        }

    except HTTPException:
        raise
    except Exception as e:
        # Clean up file if error
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Error uploading book: {str(e)}")


@router.get("/")
async def list_books():
    """Get all books with reading progress and real audio cache count."""
    try:
        books = get_all_books()
        # Override audio_cached with actual file count (not stale DB data)
        for book in books:
            book['audio_cached'] = sum(
                1 for i in range(book['total_segments'])
                if (AUDIO_CACHE_DIR / f"{book['id']}_{i}.wav").exists()
                or (AUDIO_CACHE_DIR / f"{book['id']}_{i}.mp3").exists()
            )
        return {"books": books, "total": len(books)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{book_id}")
async def get_book_detail(book_id: int):
    """Get book details including all segments."""
    try:
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        segments = get_segments(book_id)
        current_segment = get_reading_progress(book_id)

        return {
            "book": dict(book),
            "segments": segments,
            "current_segment": current_segment,
            "total_segments": len(segments)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{book_id}")
async def delete_book_handler(book_id: int):
    """Delete a book and its audio cache."""
    try:
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        # Delete audio cache files
        audio_cache_dir = Path(__file__).parent.parent / "data" / "audio_cache"
        for audio_file in audio_cache_dir.glob(f"{book_id}_*"):
            audio_file.unlink()

        # Delete book file if it exists
        if Path(book['file_path']).exists():
            Path(book['file_path']).unlink()

        # Delete from database
        delete_book(book_id)

        return {"success": True, "message": "Book deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
