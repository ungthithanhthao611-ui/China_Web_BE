from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCaseUsedProductRead(StrictSchema):
    id: str
    name: str
    slug: str
    note: str | None = None
    href: str | None = None


class ProjectCaseItemRead(StrictSchema):
    id: str
    slug: str
    anchor: str
    title: str
    summary: str
    detailHref: str
    legacyDetailHref: str | None = None
    coverImage: str | None = None
    leftGallery: list[str] = Field(default_factory=list)
    rightGallery: list[str] = Field(default_factory=list)
    layoutVariant: str
    projectYear: int | None = None
    location: str | None = None
    usedProducts: list[ProjectCaseUsedProductRead] = Field(default_factory=list)


class ProjectCaseCategoryRead(StrictSchema):
    id: str
    name: str
    slug: str
    description: str = ""
    projectCount: int = 0


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
