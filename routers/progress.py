from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import get_reading_progress, set_reading_progress, get_book

router = APIRouter(prefix="/progress", tags=["progress"])

class ProgressUpdate(BaseModel):
    segment: int

@router.get("/{book_id}")
async def get_progress(book_id: int):
    """Get reading progress for a book."""
    try:
        # Verify book exists
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        current_segment = get_reading_progress(book_id)
        return {
            "book_id": book_id,
            "current_segment": current_segment,
            "total_segments": book['total_segments']
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{book_id}")
async def update_progress(book_id: int, progress: ProgressUpdate):
    """Update reading progress for a book."""
    try:
        # Verify book exists
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        # Validate segment index
        if progress.segment < 0 or progress.segment >= book['total_segments']:
            raise HTTPException(status_code=400, detail="Invalid segment index")

        set_reading_progress(book_id, progress.segment)
        return {
            "success": True,
            "book_id": book_id,
            "current_segment": progress.segment
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{book_id}/reset")
async def reset_progress(book_id: int):
    """Reset reading progress to the beginning of the book."""
    try:
        # Verify book exists
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        set_reading_progress(book_id, 0)
        return {
            "success": True,
            "book_id": book_id,
            "current_segment": 0
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
