from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_user
from app.models.admin import AdminUser
from app.schemas.onlyoffice import OnlyOfficeCallbackPayload, OnlyOfficeConfigResponse, PostDocumentConvertResponse, PostDocumentRead
from app.services.document_conversion import convert_post_document_html
from app.services.onlyoffice import build_onlyoffice_config, handle_onlyoffice_callback
from app.services.post_documents import ensure_post_document, replace_post_document_from_upload

router = APIRouter()


@router.get("/posts/{post_id}/document", response_model=PostDocumentRead, dependencies=[Depends(require_admin_user)])
def get_post_document(post_id: int, db: Session = Depends(get_db)) -> PostDocumentRead:
    document = ensure_post_document(db=db, post_id=post_id)
    return PostDocumentRead.model_validate(document)


@router.post("/posts/{post_id}/document", response_model=PostDocumentRead, dependencies=[Depends(require_admin_user)])
async def upload_post_document(
    post_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PostDocumentRead:
    document = await replace_post_document_from_upload(db=db, post_id=post_id, file=file)
    return PostDocumentRead.model_validate(document)


@router.get("/posts/{post_id}/onlyoffice-config", response_model=OnlyOfficeConfigResponse)
def get_post_onlyoffice_config(
    post_id: int,
    db: Session = Depends(get_db),
    admin_user: AdminUser = Depends(require_admin_user),
) -> OnlyOfficeConfigResponse:
    return build_onlyoffice_config(db=db, post_id=post_id, admin_user=admin_user)


@router.post("/posts/{post_id}/convert-html", response_model=PostDocumentConvertResponse, dependencies=[Depends(require_admin_user)])
def convert_post_document_to_html(post_id: int, db: Session = Depends(get_db)) -> PostDocumentConvertResponse:
    return convert_post_document_html(db=db, post_id=post_id)


@router.post("/onlyoffice/callback", status_code=status.HTTP_200_OK)
async def onlyoffice_callback(
    payload: OnlyOfficeCallbackPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await handle_onlyoffice_callback(db=db, payload=payload, headers=request.headers)
