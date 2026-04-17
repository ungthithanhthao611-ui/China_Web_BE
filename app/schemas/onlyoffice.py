from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PostDocumentRead(ORMModel):
    id: int
    post_id: int
    file_name: str
    file_path: str
    file_url: str | None
    document_key: str
    version: int
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OnlyOfficeConfigResponse(BaseModel):
    document_server_url: str
    config: dict[str, Any]
    document: PostDocumentRead


class OnlyOfficeCallbackPayload(BaseModel):
    key: str
    status: int
    url: str | None = None
    users: list[str] = []
    actions: list[dict[str, Any]] = []
    userdata: str | None = None
    token: str | None = None


class PostDocumentConvertResponse(BaseModel):
    post_id: int
    document_id: int
    content_html: str
    converted_at: datetime
