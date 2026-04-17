from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.wordpress_sync import WordPressSyncRequest
from app.services.wordpress_sync import sync_wordpress_posts

logger = logging.getLogger("china_web_api.wordpress_sync_scheduler")
_sync_lock = asyncio.Lock()


def _build_sync_request() -> WordPressSyncRequest:
    return WordPressSyncRequest(
        language_code=settings.wp_auto_sync_language_code,
        status=settings.wp_auto_sync_status,
        per_page=settings.wp_auto_sync_per_page,
        max_pages=settings.wp_auto_sync_max_pages,
    )


async def _run_sync_once() -> None:
    if _sync_lock.locked():
        logger.warning("Skipping WordPress auto-sync because previous sync job is still running.")
        return

    async with _sync_lock:
        db = SessionLocal()
        try:
            payload = _build_sync_request()
            result = await sync_wordpress_posts(db=db, payload=payload)
            logger.info(
                "WordPress auto-sync done: fetched=%s created=%s updated=%s errors=%s",
                result.fetched_posts,
                result.posts_created,
                result.posts_updated,
                len(result.errors),
            )
            if result.errors:
                logger.warning("WordPress auto-sync partial errors: %s", result.errors[:5])
        except Exception as exc:
            logger.exception("WordPress auto-sync failed: %s", exc)
        finally:
            db.close()


async def wordpress_sync_scheduler_loop(stop_event: asyncio.Event) -> None:
    interval = max(30, int(settings.wp_auto_sync_interval_seconds))
    logger.info("WordPress auto-sync scheduler started (interval=%ss).", interval)

    while not stop_event.is_set():
        await _run_sync_once()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue

    logger.info("WordPress auto-sync scheduler stopped.")
