from pydantic import BaseModel, Field


class WordPressSyncRequest(BaseModel):
    language_code: str = Field(default="en", min_length=2, max_length=10)
    status: str = Field(default="publish", min_length=3, max_length=30)
    per_page: int = Field(default=50, ge=1, le=100)
    max_pages: int = Field(default=10, ge=1, le=200)


class WordPressSyncResult(BaseModel):
    categories_created: int = 0
    categories_updated: int = 0
    posts_created: int = 0
    posts_updated: int = 0
    posts_deleted: int = 0
    media_created: int = 0
    media_updated: int = 0
    fetched_posts: int = 0
    errors: list[str] = Field(default_factory=list)
