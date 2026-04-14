from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.services.catalog import ENTITY_REGISTRY, EntityRegistration


def get_registration(entity_name: str) -> EntityRegistration:
    registration = ENTITY_REGISTRY.get(entity_name)
    if not registration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_name}' is not registered.",
        )
    return registration


def serialize(record: Any, registration: EntityRegistration) -> dict[str, Any]:
    return registration.read_schema.model_validate(record).model_dump(mode="json")


def get_admin_entity_names() -> list[str]:
    return sorted(ENTITY_REGISTRY.keys())


def list_entity_records(
    db: Session,
    entity_name: str,
    skip: int,
    limit: int,
    language_id: int | None,
    status_value: str | None,
    is_active: bool | None,
    search: str | None,
) -> dict[str, Any]:
    registration = get_registration(entity_name)
    model = registration.model
    query = select(model)
    count_query = select(func.count()).select_from(model)

    for candidate, value in {
        "language_id": language_id,
        "status": status_value,
        "is_active": is_active,
    }.items():
        if value is not None and hasattr(model, candidate):
            column = getattr(model, candidate)
            query = query.where(column == value)
            count_query = count_query.where(column == value)

    if search:
        search_columns = [
            getattr(model, field_name)
            for field_name in ("title", "name", "slug", "config_key", "email")
            if hasattr(model, field_name)
        ]
        if search_columns:
            conditions = [cast(column, String).ilike(f"%{search}%") for column in search_columns]
            query = query.where(or_(*conditions))
            count_query = count_query.where(or_(*conditions))

    if hasattr(model, "sort_order"):
        query = query.order_by(getattr(model, "sort_order"), getattr(model, "id"))
    else:
        query = query.order_by(getattr(model, "id").desc())

    total = db.scalar(count_query) or 0
    records = db.scalars(query.offset(skip).limit(limit)).all()
    return {
        "items": [serialize(record, registration) for record in records],
        "pagination": {"skip": skip, "limit": limit, "total": total},
    }


def create_entity_record(db: Session, entity_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    registration = get_registration(entity_name)
    data = registration.create_schema.model_validate(payload).model_dump(exclude_none=True)
    record = registration.model(**data)
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize(record, registration)


def get_entity_record(db: Session, entity_name: str, record_id: int) -> dict[str, Any]:
    registration = get_registration(entity_name)
    record = db.get(registration.model, record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")
    return serialize(record, registration)


def update_entity_record(db: Session, entity_name: str, record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    registration = get_registration(entity_name)
    record = db.get(registration.model, record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")

    data = registration.update_schema.model_validate(payload).model_dump(exclude_unset=True, exclude_none=True)
    for field_name, value in data.items():
        setattr(record, field_name, value)

    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize(record, registration)


def delete_entity_record(db: Session, entity_name: str, record_id: int) -> None:
    registration = get_registration(entity_name)
    record = db.get(registration.model, record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")
    db.delete(record)
    db.commit()
