from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.init_db import initialize_database
from app.db.session import SessionLocal
from app.models.media import MediaAsset
from app.models.news import Post, PostCategory
from app.models.taxonomy import Language

DEMO_SOURCES: list[dict[str, str]] = [
    {
        "category_slug": "corporate-news",
        "source_url": "https://en.sinodecor.com/news_Detail/1937323008641404928.html",
        "published_at": "2025-06-24",
    },
    {
        "category_slug": "corporate-news",
        "source_url": "https://en.sinodecor.com/news_Detail/1925367804035534848.html",
        "published_at": "2025-05-12",
    },
    {
        "category_slug": "corporate-news",
        "source_url": "https://en.sinodecor.com/news_Detail/1910243262246100992.html",
        "published_at": "2025-04-03",
    },
    {
        "category_slug": "industry-dynamics",
        "source_url": "https://en.sinodecor.com/news_Detail2/1716629569984188416.html",
        "published_at": "2019-01-01",
    },
    {
        "category_slug": "industry-dynamics",
        "source_url": "https://en.sinodecor.com/news_Detail2/1716629663206789120.html",
        "published_at": "2018-01-01",
    },
    {
        "category_slug": "industry-dynamics",
        "source_url": "https://en.sinodecor.com/news_Detail2/1716625603955183616.html",
        "published_at": "2014-04-03",
    },
]


def slugify(value: str) -> str:
    normalized = (value or "").strip().lower()
    chunks: list[str] = []
    current: list[str] = []
    for character in normalized:
        if character.isalnum():
            current.append(character)
            continue
        if current:
            chunks.append("".join(current))
            current = []
    if current:
        chunks.append("".join(current))
    return "-".join(chunks)


def summarize_text(text: str, limit: int = 220) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def normalize_fragment_urls(fragment_html: str, base_url: str) -> str:
    fragment = BeautifulSoup(fragment_html, "html.parser")

    for tag in fragment.find_all(href=True):
        href = (tag.get("href") or "").strip()
        if href:
            tag["href"] = urljoin(base_url, href)
            tag["target"] = "_blank"
            tag["rel"] = "noreferrer noopener"

    for tag in fragment.find_all(src=True):
        source = (tag.get("src") or "").strip()
        if source:
            tag["src"] = urljoin(base_url, source)

    for tag in fragment.find_all(lazy=True):
        source = (tag.get("lazy") or "").strip()
        if source and not tag.get("src"):
            tag["src"] = urljoin(base_url, source)

    return "".join(str(node) for node in fragment.contents)


def parse_article(html: str, base_url: str, fallback_date: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("h1.e_h1-37")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    if not title and soup.title and soup.title.string:
        title = soup.title.string.replace("_China Decor", "").strip()
    if not title:
        raise RuntimeError(f"Cannot resolve title from {base_url}")

    date_node = soup.select_one(".e_timeFormat-32")
    published_raw = date_node.get_text(" ", strip=True) if date_node else fallback_date
    published_at = datetime.strptime(published_raw, "%Y-%m-%d")

    content_node = soup.select_one(".e_richText-34")
    if content_node is None:
        raise RuntimeError(f"Cannot resolve article body from {base_url}")

    for node in content_node.select("script, style, noscript, iframe"):
        node.decompose()

    body_html = normalize_fragment_urls(content_node.decode_contents(), base_url)
    plain_text = content_node.get_text(" ", strip=True)
    summary = summarize_text(plain_text, 260)

    image_node = soup.select_one(".e_image-4 img[lazy]") or content_node.select_one("img")
    image_url = ""
    if image_node is not None:
        image_url = urljoin(base_url, (image_node.get("lazy") or image_node.get("src") or "").strip())

    return {
        "title": title,
        "slug": slugify(title),
        "summary": summary,
        "body": body_html,
        "meta_title": title[:255],
        "meta_description": summarize_text(summary, 160),
        "published_at": published_at,
        "image_url": image_url or None,
    }


async def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ChinaCMSDemoSeeder/1.0; +https://localhost)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True, verify=False) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text


async def collect_demo_posts() -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    for item in DEMO_SOURCES:
        html = await fetch_html(item["source_url"])
        parsed = parse_article(html, item["source_url"], item["published_at"])
        parsed["category_slug"] = item["category_slug"]
        parsed["source_url"] = item["source_url"]
        posts.append(parsed)
    return posts


def upsert_media_asset(db, *, title: str, image_url: str | None) -> MediaAsset | None:
    if not image_url:
        return None

    media_uuid = f"sinodecor-demo-{hashlib.sha1(image_url.encode('utf-8')).hexdigest()[:20]}"
    record = db.scalar(select(MediaAsset).where(MediaAsset.uuid == media_uuid))
    if record is None:
        file_name = image_url.rsplit("/", 1)[-1][:255] or None
        record = MediaAsset(
            uuid=media_uuid,
            file_name=file_name,
            url=image_url,
            storage_path=f"external://sinodecor/{file_name}" if file_name else "external://sinodecor",
            asset_type="image",
            title=title[:255],
            status="active",
        )
        db.add(record)
        db.flush()
        return record

    if record.url != image_url:
        record.url = image_url
    if record.title != title[:255]:
        record.title = title[:255]
    if record.status != "active":
        record.status = "active"
    db.add(record)
    db.flush()
    return record


def seed_demo_posts(posts: list[dict[str, Any]]) -> tuple[int, int]:
    created = 0
    updated = 0

    with SessionLocal() as db:
        language = db.scalar(select(Language).where(Language.code == "en"))
        if language is None:
            raise RuntimeError("Language 'en' not found. Run base initialization first.")

        categories = {
            item.slug: item
            for item in db.scalars(
                select(PostCategory).where(PostCategory.slug.in_(["corporate-news", "industry-dynamics"]))
            ).all()
        }

        for item in posts:
            category = categories.get(item["category_slug"])
            if category is None:
                raise RuntimeError(f"Category '{item['category_slug']}' not found.")

            media = upsert_media_asset(db, title=item["title"], image_url=item["image_url"])
            record = db.scalar(select(Post).where(Post.slug == item["slug"]))

            payload = {
                "category_id": category.id,
                "title": item["title"][:255],
                "slug": item["slug"],
                "summary": item["summary"],
                "body": item["body"],
                "published_at": item["published_at"],
                "author": "Sinodecor demo import",
                "image_id": media.id if media else None,
                "language_id": language.id,
                "status": "published",
                "meta_title": item["meta_title"],
                "meta_description": item["meta_description"],
                "source_system": "demo_seed",
            }

            if record is None:
                record = Post(**payload)
                db.add(record)
                created += 1
            else:
                changed = False
                for field_name, value in payload.items():
                    if getattr(record, field_name) != value:
                        setattr(record, field_name, value)
                        changed = True
                if changed:
                    db.add(record)
                    updated += 1

        db.commit()

    return created, updated


async def main() -> None:
    initialize_database()
    posts = await collect_demo_posts()
    created, updated = seed_demo_posts(posts)
    print(f"Sinodecor demo posts seeded. Created: {created}, Updated: {updated}, Total processed: {len(posts)}")


if __name__ == "__main__":
    asyncio.run(main())
