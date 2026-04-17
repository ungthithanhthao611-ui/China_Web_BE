from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path

from docx import Document
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.news import Post
from app.schemas.onlyoffice import PostDocumentConvertResponse
from app.services.post_documents import ensure_post_document, resolve_absolute_file_path

try:
    import mammoth  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    mammoth = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _paragraph_style_to_tag(style_name: str) -> str:
    normalized = (style_name or "").strip().lower()
    if normalized.startswith("heading 1"):
        return "h1"
    if normalized.startswith("heading 2"):
        return "h2"
    if normalized.startswith("heading 3"):
        return "h3"
    if normalized.startswith("heading 4"):
        return "h4"
    return "p"


def convert_docx_file_to_html(file_path: Path) -> str:
    if mammoth is not None:
        with file_path.open("rb") as source:
            result = mammoth.convert_to_html(source)
        return result.value or "<p></p>"

    document = Document(file_path)
    chunks: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        tag = _paragraph_style_to_tag(getattr(paragraph.style, "name", ""))
        chunks.append(f"<{tag}>{escape(text)}</{tag}>")
    return "".join(chunks) or "<p></p>"


def convert_post_document_html(db: Session, post_id: int) -> PostDocumentConvertResponse:
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")

    document = ensure_post_document(db=db, post_id=post_id)
    file_path = resolve_absolute_file_path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word document file not found.")

    html = convert_docx_file_to_html(file_path)
    converted_at = _utc_now()

    # Keep `body` in sync for the current admin/public flow while `content_html` becomes the new source.
    post.content_html = html
    post.body = html
    document.last_synced_at = converted_at

    db.add(post)
    db.add(document)
    db.commit()
    db.refresh(document)

    return PostDocumentConvertResponse(
        post_id=post.id,
        document_id=document.id,
        content_html=html,
        converted_at=converted_at,
    )
