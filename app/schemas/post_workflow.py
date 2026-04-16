from pydantic import BaseModel, HttpUrl


class PostSourceFetchRequest(BaseModel):
    url: HttpUrl
    source_name: str | None = None
    note: str | None = None


class PostWorkflowDraft(BaseModel):
    title: str
    slug: str
    summary: str | None = None
    body: str
    meta_title: str | None = None
    meta_description: str | None = None
    author: str | None = None


class CategorySuggestionMixin(BaseModel):
    suggested_category_slug: str | None = None
    suggested_category_label: str | None = None
    category_confidence: float | None = None
    category_reason: str | None = None


class PostSourcePreview(CategorySuggestionMixin):
    url: str
    hostname: str
    source_name: str | None = None
    title: str | None = None
    excerpt: str | None = None
    plain_text: str | None = None
    html: str | None = None
    source_label: str = 'reference'
    readability_score: int | None = None
    note: str | None = None
    draft: PostWorkflowDraft


class ImportedFileMeta(BaseModel):
    file_name: str
    mime_type: str | None = None
    extension: str | None = None
    detected_format: str
    character_count: int


class PostImportPreview(CategorySuggestionMixin):
    file: ImportedFileMeta
    title: str
    summary: str | None = None
    body: str
    plain_text: str | None = None
    draft: PostWorkflowDraft
