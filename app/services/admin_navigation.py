from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.navigation import Menu, MenuItem
from app.schemas.admin_navigation import (
    AdminNavigationItemInput,
    AdminNavigationItemRead,
    AdminNavigationMenuCreate,
    AdminNavigationMenuRead,
    AdminNavigationMenuUpdate,
)


def _build_menu_tree(items: Iterable[MenuItem]) -> list[AdminNavigationItemRead]:
    nodes: dict[int, AdminNavigationItemRead] = {}
    roots: list[AdminNavigationItemRead] = []

    sorted_items = sorted(items, key=lambda item: (item.sort_order, item.id))
    for item in sorted_items:
        nodes[item.id] = AdminNavigationItemRead(
            id=item.id,
            parent_id=item.parent_id,
            title=item.title,
            url=item.url,
            target=item.target,
            item_type=item.item_type,
            page_id=item.page_id,
            anchor=item.anchor,
            sort_order=item.sort_order,
            children=[],
        )

    for item in sorted_items:
        node = nodes[item.id]
        if item.parent_id and item.parent_id in nodes:
            nodes[item.parent_id].children.append(node)
        else:
            roots.append(node)

    return roots


def _serialize_menu(menu: Menu) -> AdminNavigationMenuRead:
    return AdminNavigationMenuRead(
        id=menu.id,
        name=menu.name,
        location=menu.location,
        language_id=menu.language_id,
        is_active=menu.is_active,
        created_at=menu.created_at,
        updated_at=menu.updated_at,
        items=_build_menu_tree(menu.items),
    )


def get_navigation_menu_or_404(db: Session, menu_id: int) -> Menu:
    menu = db.scalar(select(Menu).options(selectinload(Menu.items)).where(Menu.id == menu_id))
    if not menu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found.")
    return menu


def list_navigation_menus(
    db: Session,
    language_id: int | None = None,
    location: str | None = None,
    is_active: bool | None = None,
) -> list[AdminNavigationMenuRead]:
    query = select(Menu).options(selectinload(Menu.items))

    if language_id is not None:
        query = query.where(Menu.language_id == language_id)
    if location is not None:
        query = query.where(Menu.location == location)
    if is_active is not None:
        query = query.where(Menu.is_active == is_active)

    menus = db.scalars(query.order_by(Menu.location, Menu.id)).all()
    return [_serialize_menu(menu) for menu in menus]


def create_navigation_menu(db: Session, payload: AdminNavigationMenuCreate) -> AdminNavigationMenuRead:
    record = Menu(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    db.refresh(record, attribute_names=["items"])
    return _serialize_menu(record)


def update_navigation_menu(db: Session, menu_id: int, payload: AdminNavigationMenuUpdate) -> AdminNavigationMenuRead:
    record = get_navigation_menu_or_404(db=db, menu_id=menu_id)

    for field_name, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(record, field_name, value)

    db.add(record)
    db.commit()
    db.refresh(record)
    db.refresh(record, attribute_names=["items"])
    return _serialize_menu(record)


def delete_navigation_menu(db: Session, menu_id: int) -> None:
    record = get_navigation_menu_or_404(db=db, menu_id=menu_id)
    db.delete(record)
    db.commit()


def replace_navigation_menu_tree(
    db: Session,
    menu_id: int,
    items: list[AdminNavigationItemInput],
) -> AdminNavigationMenuRead:
    menu = get_navigation_menu_or_404(db=db, menu_id=menu_id)
    existing_items_by_id = {item.id: item for item in menu.items}
    visited_ids: set[int] = set()

    def upsert_nodes(nodes: list[AdminNavigationItemInput], parent_id: int | None) -> None:
        for index, node in enumerate(nodes):
            sort_order = node.sort_order if node.sort_order is not None else index * 10

            if node.id is not None:
                record = existing_items_by_id.get(node.id)
                if not record:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Menu item #{node.id} not found in menu #{menu_id}.",
                    )
                visited_ids.add(record.id)
            else:
                record = MenuItem(menu_id=menu.id, parent_id=parent_id, title=node.title, url=node.url)
                db.add(record)
                db.flush()
                visited_ids.add(record.id)

            record.menu_id = menu.id
            record.parent_id = parent_id
            record.title = node.title
            record.url = node.url
            record.target = node.target
            record.item_type = node.item_type
            record.page_id = node.page_id
            record.anchor = node.anchor
            record.sort_order = sort_order

            upsert_nodes(node.children, parent_id=record.id)

    upsert_nodes(items, parent_id=None)

    stale_items = [item for item in menu.items if item.id not in visited_ids]

    # Break self-references first (parent_id -> menu_items.id), then delete stale rows.
    for item in stale_items:
        item.parent_id = None
    db.flush()

    for item in stale_items:
        db.delete(item)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to save navigation tree due to invalid parent/child references.",
        ) from exc

    db.expire_all()
    return _serialize_menu(get_navigation_menu_or_404(db=db, menu_id=menu_id))
