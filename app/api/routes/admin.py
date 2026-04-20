from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_user
from app.schemas.admin_navigation import (
    AdminNavigationMenuCreate,
    AdminNavigationMenuRead,
    AdminNavigationMenuUpdate,
    AdminNavigationTreeReplacePayload,
)
from app.services.admin import (
    create_entity_record,
    delete_entity_record,
    get_admin_entity_names,
    get_entity_record,
    list_entity_records,
    update_entity_record,
)
from app.services.admin_navigation import (
    create_navigation_menu,
    delete_navigation_menu,
    list_navigation_menus,
    replace_navigation_menu_tree,
    update_navigation_menu,
)
from app.services.media import create_uploaded_media_asset

router = APIRouter(dependencies=[Depends(require_admin_user)])


@router.get("/entities")
def list_entities() -> dict[str, list[str]]:
    return {"entities": get_admin_entity_names()}


@router.get("/navigation/menus")
def list_navigation(
    db: Session = Depends(get_db),
    language_id: int | None = Query(default=None),
    location: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> dict[str, list[AdminNavigationMenuRead]]:
    return {
        "items": list_navigation_menus(
            db=db,
            language_id=language_id,
            location=location,
            is_active=is_active,
        )
    }


@router.post("/navigation/menus", status_code=status.HTTP_201_CREATED)
def create_navigation(
    payload: AdminNavigationMenuCreate,
    db: Session = Depends(get_db),
) -> AdminNavigationMenuRead:
    return create_navigation_menu(db=db, payload=payload)


@router.put("/navigation/menus/{menu_id}")
def update_navigation(
    menu_id: int,
    payload: AdminNavigationMenuUpdate,
    db: Session = Depends(get_db),
) -> AdminNavigationMenuRead:
    return update_navigation_menu(db=db, menu_id=menu_id, payload=payload)


@router.put("/navigation/menus/{menu_id}/tree")
def replace_navigation_tree(
    menu_id: int,
    payload: AdminNavigationTreeReplacePayload,
    db: Session = Depends(get_db),
) -> AdminNavigationMenuRead:
    return replace_navigation_menu_tree(db=db, menu_id=menu_id, items=payload.items)


@router.delete("/navigation/menus/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_navigation(menu_id: int, db: Session = Depends(get_db)) -> None:
    delete_navigation_menu(db=db, menu_id=menu_id)


@router.post('/media/upload', status_code=status.HTTP_201_CREATED)
async def upload_media_asset(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    alt_text: str | None = Form(default=None),
    asset_folder: str | None = Form(default=None),
    public_id_base: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await create_uploaded_media_asset(
        db=db,
        file=file,
        title=title,
        alt_text=alt_text,
        asset_folder=asset_folder,
        public_id_base=public_id_base,
    )


@router.get('/{entity_name}')
def list_entity(
    entity_name: str,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    language_id: int | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1),
) -> dict[str, Any]:
    return list_entity_records(
        db=db,
        entity_name=entity_name,
        skip=skip,
        limit=limit,
        language_id=language_id,
        status_value=status_value,
        is_active=is_active,
        search=search,
    )


@router.post("/{entity_name}", status_code=status.HTTP_201_CREATED)
def create_entity(
    entity_name: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return create_entity_record(db=db, entity_name=entity_name, payload=payload)


@router.get("/{entity_name}/{record_id}")
def get_entity(entity_name: str, record_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_entity_record(db=db, entity_name=entity_name, record_id=record_id)


@router.put("/{entity_name}/{record_id}")
def update_entity(
    entity_name: str,
    record_id: int,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return update_entity_record(
        db=db,
        entity_name=entity_name,
        record_id=record_id,
        payload=payload,
    )


@router.delete("/{entity_name}/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity(entity_name: str, record_id: int, db: Session = Depends(get_db)) -> None:
    delete_entity_record(db=db, entity_name=entity_name, record_id=record_id)
