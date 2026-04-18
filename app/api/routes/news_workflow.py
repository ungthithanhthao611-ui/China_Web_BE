from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi import status as http_status
from fastapi.exceptions import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_user
from app.models.admin import AdminUser
from app.schemas.news_workflow import (
    NewsPostListQuery,
    NewsPostPayload,
    NewsPostUpdatePayload,
    NewsPublishPayload,
    SourceImportApplyPayload,
    SourceImportCreatePayload,
)
from app.services.news_workflow import (
    apply_source_import_job,
    archive_admin_news,
    create_admin_news,
    create_source_import_job,
    delete_admin_news,
    get_admin_news_detail,
    list_news_categories,
    get_admin_news_versions,
    get_public_news_detail,
    get_source_import_job,
    list_admin_news,
    list_news_images,
    list_public_news,
    publish_admin_news,
    unpublish_admin_news,
    update_admin_news,
    upload_news_image,
)
from app.utils.api_response import error_response, success_response

logger = logging.getLogger("china_web_api.news_workflow")

admin_news_router = APIRouter(prefix="/admin/news", tags=["news-workflow"])
admin_media_router = APIRouter(prefix="/admin/media", tags=["news-workflow"])
public_news_router = APIRouter(prefix="/news", tags=["news-workflow"])


def _handle_error(exc: Exception):
    if isinstance(exc, ValidationError):
        return error_response("Validation failed.", errors=exc.errors(), status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(detail, status_code=exc.status_code)

    logger.exception("Unhandled error in news workflow route")
    return error_response("Internal server error.", errors=str(exc), status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


@admin_news_router.post("")
async def create_news_post(
    payload: NewsPostPayload,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_user),
):
    try:
        result = create_admin_news(db=db, payload=payload, actor=current_user)
        return success_response(result, "News post created.", status_code=http_status.HTTP_201_CREATED)
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.put("/{post_id}")
async def update_news_post(
    post_id: int,
    payload: NewsPostUpdatePayload,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_user),
):
    try:
        result = update_admin_news(db=db, post_id=post_id, payload=payload, actor=current_user)
        return success_response(result, "News post updated.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.get("/categories")
async def list_news_post_categories(db: Session = Depends(get_db), _: AdminUser = Depends(require_admin_user)):
    try:
        result = list_news_categories(db=db)
        return success_response(result, "News categories fetched.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.get("/{post_id}")
async def get_news_post(post_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(require_admin_user)):
    try:
        result = get_admin_news_detail(db=db, post_id=post_id)
        return success_response(result, "News post fetched.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.get("")
async def list_news_posts(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    category_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin_user),
):
    try:
        query = NewsPostListQuery(page=page, limit=limit, keyword=keyword, status=status, category_id=category_id)
        result = list_admin_news(db=db, query=query)
        return success_response(result, "News posts fetched.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.delete("/{post_id}")
async def delete_news_post(post_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(require_admin_user)):
    try:
        delete_admin_news(db=db, post_id=post_id)
        return success_response(None, "News post deleted.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.post("/{post_id}/publish")
async def publish_news_post(
    post_id: int,
    payload: NewsPublishPayload = NewsPublishPayload(),
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_user),
):
    try:
        result = publish_admin_news(
            db=db,
            post_id=post_id,
            actor=current_user,
            force_generate_html=payload.force_generate_html,
        )
        return success_response(result, "News post published.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.post("/{post_id}/unpublish")
async def unpublish_news_post(post_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(require_admin_user)):
    try:
        result = unpublish_admin_news(db=db, post_id=post_id)
        return success_response(result, "News post moved to draft.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.post("/{post_id}/archive")
async def archive_news_post(post_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(require_admin_user)):
    try:
        result = archive_admin_news(db=db, post_id=post_id)
        return success_response(result, "News post moved to draft.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.get("/{post_id}/versions")
async def get_news_post_versions(post_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(require_admin_user)):
    try:
        result = get_admin_news_versions(db=db, post_id=post_id)
        return success_response(result, "News versions fetched.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.post("/import-source")
async def import_news_source(
    payload: SourceImportCreatePayload,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_user),
):
    try:
        result = await create_source_import_job(db=db, payload=payload, actor=current_user)
        return success_response(
            result,
            "Source imported into draft blocks. Manual editing is required before publish.",
            status_code=http_status.HTTP_201_CREATED,
        )
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.get("/import-source/{job_id}")
async def get_import_source_job(job_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(require_admin_user)):
    try:
        result = get_source_import_job(db=db, job_id=job_id)
        return success_response(result, "Import job fetched.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_news_router.post("/import-source/{job_id}/apply")
async def apply_import_source_job(
    job_id: int,
    payload: SourceImportApplyPayload,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin_user),
):
    try:
        result = apply_source_import_job(db=db, job_id=job_id, payload=payload)
        return success_response(result, "Imported blocks applied as draft.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_media_router.post("/upload-image")
async def upload_image_for_news(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    alt_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_user),
):
    try:
        payload = await upload_news_image(db=db, actor=current_user, file=file, title=title, alt_text=alt_text)
        return success_response(payload, "Image uploaded.", status_code=http_status.HTTP_201_CREATED)
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@admin_media_router.get("/images")
async def list_uploaded_images(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin_user),
):
    try:
        payload = list_news_images(db=db, page=page, limit=limit)
        return success_response(payload, "Images fetched.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@public_news_router.get("")
async def list_news_public(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    category_slug: str | None = Query(default=None),
    skip: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
):
    try:
        payload = list_public_news(
            db=db,
            page=page,
            limit=limit,
            category_slug=category_slug,
            skip=skip,
        )
        return success_response(payload, "Public news fetched.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)


@public_news_router.get("/{slug}")
async def get_news_public(slug: str, db: Session = Depends(get_db)):
    try:
        payload = get_public_news_detail(db=db, slug=slug)
        return success_response(payload, "Public news detail fetched.")
    except Exception as exc:  # noqa: BLE001
        return _handle_error(exc)
