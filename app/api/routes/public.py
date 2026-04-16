from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.public import (
    get_bootstrap_payload,
    get_branch_detail,
    get_page_detail,
    get_post_detail,
    get_project_detail,
    list_banners,
    list_branches,
    list_contacts,
    list_honors,
    list_posts,
    list_projects,
    list_videos,
)

router = APIRouter()


@router.get("/bootstrap")
def bootstrap(language_code: str = Query(default="en"), db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_bootstrap_payload(db=db, language_code=language_code)


@router.get("/banners")
def banners(
    language_code: str = Query(default="en"),
    banner_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"items": list_banners(db=db, language_code=language_code, banner_type=banner_type)}


@router.get("/pages/{slug}")
def page_detail(slug: str, language_code: str = Query(default="en"), db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_page_detail(db=db, slug=slug, language_code=language_code)


@router.get("/posts")
def posts(
    language_code: str = Query(default="en"),
    category_slug: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=12, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return list_posts(
        db=db,
        language_code=language_code,
        category_slug=category_slug,
        skip=skip,
        limit=limit,
    )


@router.get("/posts/{slug}")
def post_detail(slug: str, language_code: str = Query(default="en"), db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_post_detail(db=db, slug=slug, language_code=language_code)


@router.get("/projects")
def projects(
    language_code: str = Query(default="en"),
    category_slug: str | None = Query(default=None),
    year: int | None = Query(default=None, ge=1900, le=2100),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=12, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return list_projects(
        db=db,
        language_code=language_code,
        category_slug=category_slug,
        year=year,
        skip=skip,
        limit=limit,
    )


@router.get("/projects/{slug}")
def project_detail(
    slug: str,
    language_code: str = Query(default="en"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_project_detail(db=db, slug=slug, language_code=language_code)


@router.get("/honors")
def honors(
    language_code: str = Query(default="en"),
    award_year: int | None = Query(default=None, ge=1900, le=2100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return list_honors(db=db, language_code=language_code, award_year=award_year)


@router.get("/branches")
def branches(
    language_code: str = Query(default="en"),
    branch_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"items": list_branches(db=db, language_code=language_code, branch_type=branch_type)}


@router.get("/branches/{slug}")
def branch_detail(
    slug: str,
    language_code: str = Query(default="en"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_branch_detail(db=db, slug=slug, language_code=language_code)


@router.get("/contacts")
def contacts(language_code: str = Query(default="en"), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": list_contacts(db=db, language_code=language_code)}


@router.get("/videos")
def videos(language_code: str = Query(default="en"), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": list_videos(db=db, language_code=language_code)}
