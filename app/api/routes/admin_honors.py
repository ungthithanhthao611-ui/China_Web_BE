from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_user
from app.models.admin import AdminUser
from app.schemas.honors import (
    HonorCategoryCreateDTO,
    HonorCategoryUpdateDTO,
    HonorCreateDTO,
    HonorToggleActiveDTO,
    HonorUpdateDTO,
)
from app.services.honors import (
    create_admin_honor,
    create_admin_honor_category,
    get_admin_honor,
    list_admin_honor_categories,
    list_admin_honors,
    resync_admin_honor_images_to_cloudinary,
    soft_delete_admin_honor,
    soft_delete_admin_honor_category,
    toggle_admin_honor_active,
    update_admin_honor,
    update_admin_honor_category,
)

router = APIRouter(dependencies=[Depends(require_admin_user)])


@router.get("/honors/categories")
def get_honor_categories(
    keyword: str | None = Query(default=None, min_length=1),
    is_active: bool | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    items = list_admin_honor_categories(
        db=db,
        keyword=keyword,
        is_active=is_active,
        include_deleted=include_deleted,
    )
    return {"items": items}


@router.post("/honors/categories", status_code=status.HTTP_201_CREATED)
def create_honor_category(
    payload: HonorCategoryCreateDTO,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return create_admin_honor_category(db=db, payload=payload)


@router.put("/honors/categories/{category_id}")
def update_honor_category(
    category_id: int,
    payload: HonorCategoryUpdateDTO,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return update_admin_honor_category(db=db, category_id=category_id, payload=payload)


@router.delete("/honors/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_honor_category(
    category_id: int,
    db: Session = Depends(get_db),
) -> None:
    soft_delete_admin_honor_category(db=db, category_id=category_id)


@router.get("/honors")
def get_honors(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    category_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None, min_length=1),
    is_active: bool | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return list_admin_honors(
        db=db,
        skip=skip,
        limit=limit,
        category_id=category_id,
        keyword=keyword,
        is_active=is_active,
        include_deleted=include_deleted,
    )


@router.post("/honors/resync-images")
def resync_honor_images(
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return resync_admin_honor_images_to_cloudinary(db=db, actor_id=current_user.id)


@router.get("/honors/{honor_id}")
def get_honor(
    honor_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_admin_honor(db=db, honor_id=honor_id)


@router.post("/honors", status_code=status.HTTP_201_CREATED)
def create_honor(
    payload: HonorCreateDTO,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return create_admin_honor(db=db, payload=payload, actor_id=current_user.id)


@router.put("/honors/{honor_id}")
def update_honor(
    honor_id: int,
    payload: HonorUpdateDTO,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return update_admin_honor(
        db=db,
        honor_id=honor_id,
        payload=payload,
        actor_id=current_user.id,
    )


@router.patch("/honors/{honor_id}/active")
def toggle_honor_active(
    honor_id: int,
    payload: HonorToggleActiveDTO,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return toggle_admin_honor_active(
        db=db,
        honor_id=honor_id,
        payload=payload,
        actor_id=current_user.id,
    )


@router.delete("/honors/{honor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_honor(
    honor_id: int,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_user),
) -> None:
    soft_delete_admin_honor(db=db, honor_id=honor_id, actor_id=current_user.id)
