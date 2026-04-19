from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCaseItemRead(StrictSchema):
    anchor: str
    title: str
    summary: str
    detailHref: str
    legacyDetailHref: str | None = None
    leftGallery: list[str] = Field(default_factory=list)
    rightGallery: list[str] = Field(default_factory=list)
    layoutVariant: str


class ProjectCaseCategoryRead(StrictSchema):
    id: str
    name: str
    slug: str
    projects: list[ProjectCaseItemRead] = Field(default_factory=list)


class ProjectCaseCurrentCategoryRead(StrictSchema):
    id: str
    name: str
    slug: str


class ProjectCaseHeroSlideRead(StrictSchema):
    categoryId: str
    title: str
    desktopImage: str | None = None
    mobileImage: str | None = None
    summary: str


class ProjectCasePageRead(StrictSchema):
    currentCategory: ProjectCaseCurrentCategoryRead
    categories: list[ProjectCaseCategoryRead] = Field(default_factory=list)
    heroSlides: list[ProjectCaseHeroSlideRead] = Field(default_factory=list)
    cases: list[ProjectCaseItemRead] = Field(default_factory=list)
