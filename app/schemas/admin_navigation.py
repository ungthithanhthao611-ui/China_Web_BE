from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminNavigationMenuCreate(BaseModel):
    name: str
    location: str | None = None
    language_id: int
    is_active: bool = True


class AdminNavigationMenuUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    language_id: int | None = None
    is_active: bool | None = None


class AdminNavigationItemInput(BaseModel):
    id: int | None = None
    title: str
    url: str
    target: str | None = None
    item_type: str | None = None
    page_id: int | None = None
    anchor: str | None = None
    sort_order: int | None = None
    children: list["AdminNavigationItemInput"] = Field(default_factory=list)


class AdminNavigationTreeReplacePayload(BaseModel):
    items: list[AdminNavigationItemInput] = Field(default_factory=list)


class AdminNavigationItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    title: str
    url: str
    target: str | None
    item_type: str | None
    page_id: int | None
    anchor: str | None
    sort_order: int
    children: list["AdminNavigationItemRead"] = Field(default_factory=list)


class AdminNavigationMenuRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str | None
    language_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    items: list[AdminNavigationItemRead] = Field(default_factory=list)


AdminNavigationItemInput.model_rebuild()
AdminNavigationItemRead.model_rebuild()
