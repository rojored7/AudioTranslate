import pdfplumber
from ebooklib import epub
from pathlib import Path
import re

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF file."""
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return ""
    return text

def extract_text_from_epub(file_path: str) -> str:
    """Extract text from EPUB file."""
    book = epub.read_epub(file_path)
    text = ""

    for item in book.get_items():
        if item.get_type() == epub.ITEM_DOCUMENT:
            content = item.get_content()
            # Decode if bytes
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='ignore')
            # Remove HTML tags
            text += re.sub(r'<[^>]+>', '', content)
            text += "\n\n"

    return text

def extract_text_from_txt(file_path: str) -> str:
    """Extract text from plain text file."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def extract_text(file_path: str, format: str) -> str:
    """Extract text from any supported format."""
    if format == 'pdf':
        return extract_text_from_pdf(file_path)
    elif format == 'epub':
        return extract_text_from_epub(file_path)
    elif format == 'txt':
        return extract_text_from_txt(file_path)
    else:
        raise ValueError(f"Unsupported format: {format}")

def split_into_segments(text: str, max_words: int = 500) -> list[dict]:
    """Split text into segments by word count."""
    # Clean up text
    text = re.sub(r'\s+', ' ', text).strip()

    # Split by sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)

    segments = []
    current_segment = ""
    word_count = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())

        if word_count + sentence_words > max_words and current_segment:
            # Save current segment
            segments.append({
                'segment_index': len(segments),
                'text': current_segment.strip()
            })
            current_segment = ""
            word_count = 0

        current_segment += sentence + " "
        word_count += sentence_words

    # Add remaining segment
    if current_segment.strip():
        segments.append({
            'segment_index': len(segments),
            'text': current_segment.strip()
        })

    return segments

def extract_and_segment(file_path: str, format: str) -> tuple[str, list[dict]]:
    """Extract text from file and split into segments. Returns (full_text, segments)."""
    text = extract_text(file_path, format)
    segments = split_into_segments(text)
    return text, segments

def get_book_metadata(file_path: str, format: str) -> dict:
    """Try to extract book metadata (title, author)."""
    metadata = {
        'title': Path(file_path).stem,
        'author': None
    }

    if format == 'epub':
        try:
            book = epub.read_epub(file_path)
            if book.get_metadata('DC', 'title'):
                metadata['title'] = book.get_metadata('DC', 'title')[0][0]
            if book.get_metadata('DC', 'creator'):
                metadata['author'] = book.get_metadata('DC', 'creator')[0][0]
        except:
            pass

    return metadata
