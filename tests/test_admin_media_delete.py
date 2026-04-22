from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.base  # noqa: F401
from app.models.base import Base
from app.models.media import MediaAsset
from app.models.news import NewsPost
from app.models.taxonomy import Language
from app.services.admin import delete_entity_record


def make_session(tmp_path: Path):
  db_path = tmp_path / "test_media_delete.sqlite3"
  engine = create_engine(
    f"sqlite:///{db_path}",
    future=True,
    connect_args={"check_same_thread": False},
  )
  SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
  )
  Base.metadata.create_all(bind=engine)
  session = SessionLocal()
  session.add(Language(id=1, code="en", name="English", is_default=True, status="active"))
  session.commit()
  return session, engine


def test_delete_media_asset_removes_local_file(tmp_path: Path):
  session, engine = make_session(tmp_path)
  try:
    local_file = tmp_path / "uploads" / "sample.png"
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_bytes(b"image-bytes")

    record = MediaAsset(
      uuid="local-delete-1",
      file_name="sample.png",
      url="/uploads/sample.png",
      storage_path=str(local_file),
      asset_type="image",
      mime_type="image/png",
      status="active",
    )
    session.add(record)
    session.commit()

    delete_entity_record(session, "media_assets", record.id)

    assert not local_file.exists()
    assert session.get(MediaAsset, record.id) is None
  finally:
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_delete_media_asset_removes_cloudinary_asset(tmp_path: Path):
  session, engine = make_session(tmp_path)
  try:
    record = MediaAsset(
      uuid="cloudinary-delete-1",
      file_name="sample.png",
      url="https://res.cloudinary.com/demo/image/upload/v1/China-web/sample.png",
      storage_path="China-web/sample",
      asset_type="image",
      mime_type="image/png",
      status="active",
    )
    session.add(record)
    session.commit()

    with patch("app.services.media._configure_cloudinary"), patch(
      "app.services.media._has_cloudinary_configuration", return_value=True
    ), patch("app.services.media.cloudinary.uploader.destroy", return_value={"result": "ok"}) as destroy_mock:
      delete_entity_record(session, "media_assets", record.id)

    destroy_mock.assert_called_once_with(
      "China-web/sample",
      resource_type="image",
      invalidate=True,
    )
    assert session.get(MediaAsset, record.id) is None
  finally:
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_delete_media_asset_is_blocked_when_record_is_referenced(tmp_path: Path):
  session, engine = make_session(tmp_path)
  try:
    media = MediaAsset(
      uuid="media-ref-1",
      file_name="post-image.png",
      url="/uploads/post-image.png",
      storage_path=str(tmp_path / "uploads" / "post-image.png"),
      asset_type="image",
      mime_type="image/png",
      status="active",
    )
    session.add(media)
    session.commit()

    session.add(
      NewsPost(
        title="Post using media",
        slug="post-using-media",
        image_id=media.id,
        status="published",
      )
    )
    session.commit()

    try:
      delete_entity_record(session, "media_assets", media.id)
    except HTTPException as exc:
      assert exc.status_code == 409
      assert "posts.image_id" in str(exc.detail)
    else:
      raise AssertionError("Expected delete_entity_record to block referenced media asset deletion.")

    assert session.get(MediaAsset, media.id) is not None
  finally:
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
