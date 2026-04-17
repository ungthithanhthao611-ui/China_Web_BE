from __future__ import annotations

import mimetypes
import sys
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cloudinary
import cloudinary.uploader
import requests
import urllib3
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.content import Banner
from app.models.media import MediaAsset
from app.models.taxonomy import Language

SOURCE_PAGE_URL = "https://en.sinodecor.com/"
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PC_BANNER_BLOCK_PATTERN = re.compile(
    r'<div class="swiper-container index_banner pc_banner.*?<div class="swiper-wrapper">(.*?)</div>\s*<div class="swiper-pagination',
    re.S,
)
PC_SLIDE_PATTERN = re.compile(
    r'<div class="swiper-slide">\s*'
    r'(?:(?:<div class="banner-video">\s*<video src="(?P<video_src>[^"]+)".*?</video>.*?</div>)|'
    r'(?:<div class="img">\s*<img src="(?P<image_src>[^"]+)" alt="(?P<image_alt>[^"]*)"[^>]*>.*?</div>))'
    r'.*?</div>',
    re.S,
)


@dataclass
class BannerAsset:
    index: int
    asset_type: str
    source_url: str
    alt_text: str
    title: str
    file_stem: str
    public_id: str


def configure_cloudinary() -> None:
    if settings.cloudinary_url.strip():
        cloudinary.config(cloudinary_url=settings.cloudinary_url, secure=True)
        return

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    normalized = normalized.strip("-")
    return normalized or f"banner-{uuid.uuid4().hex[:8]}"


def crawl_home_banner_assets() -> list[BannerAsset]:
    response = requests.get(SOURCE_PAGE_URL, timeout=60, verify=False)
    response.raise_for_status()

    block_match = PC_BANNER_BLOCK_PATTERN.search(response.text)
    if not block_match:
        raise RuntimeError("Could not locate the desktop banner slider on the source homepage.")

    assets: list[BannerAsset] = []
    for index, match in enumerate(PC_SLIDE_PATTERN.finditer(block_match.group(1)), start=1):
        video_src = (match.group("video_src") or "").strip()
        image_src = (match.group("image_src") or "").strip()
        is_video = bool(video_src)
        source_url = urljoin(SOURCE_PAGE_URL, video_src or image_src)
        asset_type = "video" if is_video else "image"
        type_label = "Video" if is_video else "Image"
        title = f"Homepage Banner {index:02d} {type_label}"
        file_stem = slugify(title)
        assets.append(
            BannerAsset(
                index=index,
                asset_type=asset_type,
                source_url=source_url,
                alt_text=(match.group("image_alt") or "").strip() or f"Homepage banner {index:02d}",
                title=title,
                file_stem=file_stem,
                public_id=file_stem,
            )
        )

    if not assets:
        raise RuntimeError("No banner assets were parsed from the source homepage.")

    return assets


def fetch_remote_metadata(url: str) -> tuple[int | None, str | None]:
    try:
        response = requests.head(url, timeout=60, allow_redirects=True, verify=False)
        response.raise_for_status()
        size_raw = response.headers.get("content-length")
        mime_type = response.headers.get("content-type")
        return (int(size_raw) if size_raw and size_raw.isdigit() else None, mime_type)
    except Exception:
        guessed_mime, _ = mimetypes.guess_type(url)
        return (None, guessed_mime)


def download_to_temp(url: str, suffix: str) -> Path:
    response = requests.get(url, timeout=180, stream=True, verify=False)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                temp_file.write(chunk)
        return Path(temp_file.name)


def upload_asset_to_cloudinary(asset: BannerAsset) -> dict[str, Any]:
    resource_type = "video" if asset.asset_type == "video" else "image"
    asset_folder = f"{settings.cloudinary_folder.strip('/')}/banner"
    try:
        return cloudinary.uploader.upload(
            asset.source_url,
            resource_type=resource_type,
            asset_folder=asset_folder,
            public_id=asset.public_id,
            overwrite=True,
            use_filename=False,
            unique_filename=False,
            use_asset_folder_as_public_id_prefix=True,
            display_name=asset.title,
        )
    except Exception:
        suffix = Path(asset.source_url).suffix or (".mp4" if asset.asset_type == "video" else ".jpg")
        temp_file = download_to_temp(asset.source_url, suffix)
        try:
            return cloudinary.uploader.upload(
                str(temp_file),
                resource_type=resource_type,
                asset_folder=asset_folder,
                public_id=asset.public_id,
                overwrite=True,
                use_filename=False,
                unique_filename=False,
                use_asset_folder_as_public_id_prefix=True,
                display_name=asset.title,
            )
        finally:
            temp_file.unlink(missing_ok=True)


def upsert_media_asset(session: Session, asset: BannerAsset, upload_result: dict[str, Any]) -> MediaAsset:
    size, mime_type = fetch_remote_metadata(asset.source_url)
    record = session.scalar(select(MediaAsset).where(MediaAsset.storage_path == upload_result["public_id"]))
    if not record:
        record = MediaAsset(uuid=str(uuid.uuid4()))

    record.file_name = f"{asset.file_stem}.{upload_result.get('format') or ('mp4' if asset.asset_type == 'video' else 'jpg')}"
    record.url = upload_result.get("secure_url") or upload_result.get("url") or asset.source_url
    record.storage_path = upload_result["public_id"]
    record.asset_type = asset.asset_type
    record.mime_type = mime_type or ("video/mp4" if asset.asset_type == "video" else "image/jpeg")
    record.width = upload_result.get("width")
    record.height = upload_result.get("height")
    record.size = upload_result.get("bytes") or size
    record.alt_text = asset.alt_text
    record.title = asset.title
    record.status = "active"
    session.add(record)
    session.flush()
    return record


def get_default_language_id(session: Session) -> int:
    language = session.scalar(
        select(Language).where(Language.is_default.is_(True), Language.status == "active").order_by(Language.id.asc())
    )
    if not language:
        language = session.scalar(select(Language).where(Language.status == "active").order_by(Language.id.asc()))
    if not language:
        raise RuntimeError("No active language was found in the database.")
    return int(language.id)


def upsert_hero_banners(session: Session, language_id: int, media_records: list[MediaAsset]) -> list[Banner]:
    existing = session.scalars(
        select(Banner)
        .where(Banner.language_id == language_id, Banner.banner_type == "hero")
        .order_by(Banner.sort_order.asc(), Banner.id.asc())
    ).all()

    saved: list[Banner] = []
    for index, media in enumerate(media_records, start=1):
        record = existing[index - 1] if index - 1 < len(existing) else Banner(language_id=language_id, banner_type="hero")
        record.title = None
        record.subtitle = None
        record.body = None
        record.image_id = media.id
        record.link = None
        record.button_text = None
        record.banner_type = "hero"
        record.sort_order = index
        record.is_active = True
        session.add(record)
        saved.append(record)

    for record in existing[len(media_records):]:
        record.is_active = False
        record.sort_order = max(record.sort_order, 1000 + record.id)
        session.add(record)

    session.flush()
    return saved


def main() -> None:
    if settings.media_storage.strip().lower() != "cloudinary":
        raise RuntimeError("MEDIA_STORAGE must be set to cloudinary before importing homepage banners.")

    configure_cloudinary()
    assets = crawl_home_banner_assets()

    with SessionLocal() as session:
        language_id = get_default_language_id(session)
        media_records: list[MediaAsset] = []

        for asset in assets:
            upload_result = upload_asset_to_cloudinary(asset)
            media_record = upsert_media_asset(session, asset, upload_result)
            media_records.append(media_record)
            print(f"uploaded hero-{asset.index:02d} -> media #{media_record.id} ({media_record.asset_type})")

        banners = upsert_hero_banners(session, language_id, media_records)
        session.commit()

        print(f"updated {len(banners)} active hero banners for language #{language_id}")
        for banner in banners:
            print(f"banner #{banner.id} sort={banner.sort_order} image_id={banner.image_id}")


if __name__ == "__main__":
    main()
