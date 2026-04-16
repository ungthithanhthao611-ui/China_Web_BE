from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HonorCategoryCreateDTO(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    type: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    description: str | None = None
    sort_order: int = 0
    is_active: bool = True


class HonorCategoryUpdateDTO(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    type: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: int | None = None
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class HonorCategoryReadDTO(ORMModel):
    id: int
    name: str
    slug: str
    type: str
    parent_id: int | None
    description: str | None
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class HonorCreateDTO(BaseModel):
    category_id: int | None = None
    title: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    short_description: str | None = None
    image_url: str | None = Field(default=None, max_length=500)
    year: int | None = Field(default=None, ge=1900, le=2100)
    issued_by: str | None = Field(default=None, max_length=255)
    display_type: str | None = Field(default=None, max_length=100)
    sort_order: int = 0
    is_featured: bool = False
    is_active: bool = True


class HonorUpdateDTO(BaseModel):
    category_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    short_description: str | None = None
    image_url: str | None = Field(default=None, max_length=500)
    year: int | None = Field(default=None, ge=1900, le=2100)
    issued_by: str | None = Field(default=None, max_length=255)
    display_type: str | None = Field(default=None, max_length=100)
    sort_order: int | None = None
    is_featured: bool | None = None
    is_active: bool | None = None


class HonorToggleActiveDTO(BaseModel):
    is_active: bool


class HonorReadDTO(ORMModel):
    id: int
    category_id: int | None
    title: str
    slug: str
    short_description: str | None
    image_url: str | None
    year: int | None
    issued_by: str | None
    display_type: str
    sort_order: int
    is_featured: bool
    is_active: bool
    created_by: int | None
    updated_by: int | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
