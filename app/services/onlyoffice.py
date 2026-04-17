from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.admin import AdminUser
from app.models.news import Post
from app.models.post_documents import PostDocument
from app.schemas.onlyoffice import OnlyOfficeCallbackPayload, OnlyOfficeConfigResponse, PostDocumentRead
from app.services.document_conversion import convert_post_document_html
from app.services.post_documents import ensure_post_document, save_document_bytes


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}".encode("ascii"))


def _encode_jwt(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def _decode_jwt(token: str, secret: str) -> dict[str, Any]:
    try:
        header_part, payload_part, signature_part = token.split(".", 2)
        signing_input = f"{header_part}.{payload_part}"
        expected_signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_encode(expected_signature), signature_part):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ONLYOFFICE token signature.")
        return json.loads(_b64url_decode(payload_part))
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard for malformed callback tokens
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ONLYOFFICE token.") from exc


def ensure_onlyoffice_settings() -> None:
    if not (settings.onlyoffice_document_server_url or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ONLYOFFICE_DOCUMENT_SERVER_URL is not configured.")
    if not (settings.onlyoffice_callback_base_url or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ONLYOFFICE_CALLBACK_BASE_URL is not configured.")
    if not (settings.onlyoffice_jwt_secret or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ONLYOFFICE_JWT_SECRET is not configured.")


def build_onlyoffice_config(db: Session, post_id: int, admin_user: AdminUser) -> OnlyOfficeConfigResponse:
    ensure_onlyoffice_settings()

    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")

    document = ensure_post_document(db=db, post_id=post_id)
    callback_url = f"{settings.onlyoffice_callback_base_url.rstrip('/')}{settings.api_v1_prefix}/admin/onlyoffice/callback"
    payload = {
        "documentType": "word",
        "type": "desktop",
        "document": {
            "title": document.file_name,
            "url": document.file_url,
            "fileType": "docx",
            "key": document.document_key,
        },
        "editorConfig": {
            "mode": "edit",
            "callbackUrl": callback_url,
            "user": {
                "id": str(admin_user.id),
                "name": admin_user.username,
            },
            "customization": {
                "autosave": True,
                "forcesave": True,
            },
        },
    }
    payload["token"] = _encode_jwt(payload, settings.onlyoffice_jwt_secret)

    return OnlyOfficeConfigResponse(
        document_server_url=settings.onlyoffice_document_server_url.rstrip("/"),
        config=payload,
        document=PostDocumentRead.model_validate(document),
    )


def _extract_callback_token(headers: Any, payload: OnlyOfficeCallbackPayload) -> str:
    authorization = str(headers.get("authorization") or headers.get("Authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if payload.token:
        return payload.token.strip()
    return ""


def validate_onlyoffice_callback(headers: Any, payload: OnlyOfficeCallbackPayload) -> None:
    ensure_onlyoffice_settings()
    token = _extract_callback_token(headers, payload)
    if not token:
        if settings.is_production:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing ONLYOFFICE callback token.")
        return
    decoded = _decode_jwt(token, settings.onlyoffice_jwt_secret)
    document_key = str(decoded.get("document", {}).get("key") or decoded.get("key") or "").strip()
    if document_key and document_key != payload.key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ONLYOFFICE callback token key mismatch.")


async def handle_onlyoffice_callback(db: Session, payload: OnlyOfficeCallbackPayload, headers: Any) -> dict[str, int]:
    validate_onlyoffice_callback(headers=headers, payload=payload)

    if payload.status not in {2, 6}:
        return {"error": 0}

    document = db.scalar(select(PostDocument).where(PostDocument.document_key == payload.key))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ONLYOFFICE document not found.")
    if not payload.url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ONLYOFFICE callback download URL is missing.")

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        response = await client.get(payload.url)
        response.raise_for_status()

    save_document_bytes(
        db=db,
        document=document,
        file_bytes=response.content,
        file_name=document.file_name,
        increment_version=True,
    )

    if settings.onlyoffice_auto_convert_on_callback:
        convert_post_document_html(db=db, post_id=document.post_id)

    return {"error": 0}
