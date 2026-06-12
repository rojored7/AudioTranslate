from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from db import init_db
from routers import books, audio, progress, settings, export

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title="AudioBook Player",
    description="Local audiobook player with TTS support",
    version="1.0.0"
)

# Include routers
app.include_router(books.router)
app.include_router(audio.router)
app.include_router(progress.router)
app.include_router(settings.router)
app.include_router(export.router)

# Serve static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
async def root():
    """Serve the main index page."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "AudioBook Player API is running. Upload a book at POST /books/upload"}

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9001,
        log_level="info"
    )
