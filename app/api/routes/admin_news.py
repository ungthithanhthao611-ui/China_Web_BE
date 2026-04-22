"""
Admin News special endpoints: Crawl from URL
"""
import logging
import math
import re
import time
import traceback
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from app.api.deps import get_current_admin_user

router = APIRouter(prefix="/admin/news", tags=["admin-news"])
logger = logging.getLogger("china_web_api.admin_news")


class CrawlRequest(BaseModel):
    url: str


def _extract_src_from_srcset(srcset_value: str) -> str:
    """Pick a usable URL from srcset/data-srcset."""
    if not srcset_value:
        return ""
    parts = [chunk.strip() for chunk in str(srcset_value).split(",") if chunk.strip()]
    if not parts:
        return ""
    # Prefer the last candidate (often highest resolution).
    candidate = parts[-1].split()[0].strip()
    return candidate


def _normalize_image_src(image_tag, base_url: str) -> str:
    """Resolve image URL from common lazy-load attributes."""
    candidates = [
        image_tag.get("src"),
        image_tag.get("data-src"),
        image_tag.get("data-original"),
        image_tag.get("data-lazy-src"),
        image_tag.get("data-image"),
        image_tag.get("data-url"),
        _extract_src_from_srcset(image_tag.get("srcset")),
        _extract_src_from_srcset(image_tag.get("data-srcset")),
    ]

    for raw in candidates:
        src = str(raw or "").strip()
        if not src:
            continue
        lower = src.lower()
        if lower.startswith(("data:", "javascript:", "blob:", "#")):
            continue
        if src.startswith("//"):
            src = f"https:{src}"
        normalized = urljoin(base_url, src)
        if normalized.startswith(("http://", "https://")):
            return normalized
    return ""


def _is_probably_content_image(src: str) -> bool:
    lower = src.lower()
    noisy_keywords = ("logo", "icon", "sprite", "emoji", "avatar", "tracking", "pixel", "ads")
    if any(keyword in lower for keyword in noisy_keywords):
        return False
    return True


def _process_html_to_blocks(html: str, base_url: str = ""):
    """Convert HTML string to editor blocks (same logic as /new Node server)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    blocks = []
    canvas_width = 800
    page_padding = 40
    block_width = canvas_width - (page_padding * 2)
    current_y = 40

    current_text_html = ""
    current_text_length = 0
    seen_image_sources: set[str] = set()

    def flush_text():
        nonlocal current_text_html, current_text_length, current_y
        if not current_text_html.strip():
            return

        lines = math.ceil(current_text_length / 90)
        p_count = current_text_html.count("<p")
        h_count = len(re.findall(r"<h\d", current_text_html))
        li_count = current_text_html.count("<li")
        estimated_height = max(100, (lines * 26) + (p_count * 24) + (h_count * 40) + (li_count * 16) + 40)

        blocks.append(
            {
                "id": f"block-{int(time.time() * 1000)}-{len(blocks)}",
                "type": "text",
                "x": page_padding,
                "y": current_y,
                "w": block_width,
                "h": estimated_height,
                "content": current_text_html,
                "props": {
                    "fontSize": 16,
                    "color": "#111827",
                    "fontFamily": "Inter, sans-serif",
                    "textAlign": "left",
                    "lineHeight": 1.7,
                },
            }
        )
        current_y += estimated_height + 20
        current_text_html = ""
        current_text_length = 0

    for child in soup.children:
        tag = getattr(child, "name", None)
        if tag in ("img", "figure"):
            flush_text()
            img_tag = child if tag == "img" else child.find("img")
            figcaption = child.find("figcaption") if tag == "figure" else None
            if img_tag:
                src = _normalize_image_src(img_tag, base_url)
                if not src or not _is_probably_content_image(src) or src in seen_image_sources:
                    continue
                seen_image_sources.add(src)
                caption = figcaption.get_text(" ", strip=True) if figcaption else (img_tag.get("alt") or "")
                img_height = 400
                blocks.append(
                    {
                        "id": f"block-{int(time.time() * 1000)}-img-{len(blocks)}",
                        "type": "image",
                        "x": page_padding,
                        "y": current_y,
                        "w": block_width,
                        "h": img_height,
                        "content": "",
                        "props": {
                            "src": src,
                            "objectFit": "contain",
                            "borderRadius": 8,
                            "captionText": caption,
                            "captionPosition": "outside-bottom",
                        },
                    }
                )
                current_y += img_height + (40 if caption else 20)
        elif hasattr(child, "find") and (child.find("img") or child.find("figure")):
            for sub in child.children:
                if hasattr(sub, "name"):
                    if getattr(sub, "name", None) in ("img", "figure"):
                        flush_text()
                        img_tag = sub if sub.name == "img" else sub.find("img")
                        figcaption = sub.find("figcaption") if sub.name == "figure" else None
                        if img_tag:
                            src = _normalize_image_src(img_tag, base_url)
                            if not src or not _is_probably_content_image(src) or src in seen_image_sources:
                                continue
                            seen_image_sources.add(src)
                            caption = figcaption.get_text(" ", strip=True) if figcaption else (img_tag.get("alt") or "")
                            img_height = 400
                            blocks.append(
                                {
                                    "id": f"block-{int(time.time() * 1000)}-img-{len(blocks)}",
                                    "type": "image",
                                    "x": page_padding,
                                    "y": current_y,
                                    "w": block_width,
                                    "h": img_height,
                                    "content": "",
                                    "props": {
                                        "src": src,
                                        "objectFit": "contain",
                                        "borderRadius": 8,
                                        "captionText": caption,
                                        "captionPosition": "outside-bottom",
                                    },
                                }
                            )
                            current_y += img_height + (40 if caption else 20)
                    else:
                        current_text_html += str(sub) + "\n"
                        current_text_length += len(sub.get_text(" ", strip=True))
        else:
            html_str = str(child)
            if html_str.strip():
                current_text_html += html_str + "\n"
                current_text_length += len(child.get_text(" ", strip=True)) if hasattr(child, "get_text") else len(str(child))

    flush_text()
    return blocks, current_y


def _clean_article_node(node):
    for bad in node.select(
        "script, style, noscript, iframe, form, button, input, aside, nav, .banner, .ads, .advertisement, .social-share, .sidebar"
    ):
        bad.decompose()
    return node


def _extract_fallback_article_html(html: str, url: str):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")

    title = ""
    excerpt = ""
    thumbnail_url = ""

    og_title = soup.find("meta", attrs={"property": "og:title"})
    og_description = soup.find("meta", attrs={"property": "og:description"})
    og_image = soup.find("meta", attrs={"property": "og:image"})

    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    if og_description and og_description.get("content"):
        excerpt = og_description["content"].strip()

    if og_image and og_image.get("content"):
        thumbnail_url = urljoin(url, og_image["content"].strip())

    selectors = [
        "article",
        "main article",
        "main",
        "[itemprop='articleBody']",
        ".fck_detail",
        ".sidebar-1",
        ".article-content",
        ".article-body",
        ".content-detail",
        ".detail-content",
        ".news-detail",
        ".post-content",
        ".entry-content",
    ]

    article_node = None
    for selector in selectors:
        candidate = soup.select_one(selector)
        if candidate and candidate.get_text(" ", strip=True):
            article_node = candidate
            break

    if article_node is None:
        paragraphs = soup.find_all(["h1", "h2", "h3", "p", "ul", "ol", "figure", "img"])
        if paragraphs:
            wrapper = BeautifulSoup("<div></div>", "html.parser").div
            for item in paragraphs[:200]:
                wrapper.append(item)
            article_node = wrapper

    if article_node is None:
        return title, excerpt, thumbnail_url, ""

    article_node = _clean_article_node(article_node)

    for image in article_node.find_all("img"):
        src = _normalize_image_src(image, url)
        if src:
            image["src"] = src
            if not thumbnail_url:
                thumbnail_url = image["src"]
        else:
            image.decompose()

    content_html = str(article_node)
    plain_text = article_node.get_text(" ", strip=True)

    if not excerpt and plain_text:
        excerpt = plain_text[:200].strip()

    return title, excerpt, thumbnail_url, content_html


@router.post("/crawl")
async def crawl_article(
    body: CrawlRequest,
    _admin=Depends(get_current_admin_user),
):
    """Crawl article from URL using readability with robust fallback parsing."""
    import httpx

    url = (body.url or "").strip()
    if not url:
        return {"success": False, "message": "URL is required"}

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )
            resp.raise_for_status()
            html = resp.text

        readability_title = ""
        readability_html = ""
        readability_error = ""

        try:
            from readability import Document

            doc = Document(html, url=url)
            readability_title = (doc.title() or "").strip()
            readability_html = (doc.summary() or "").strip()
        except ImportError as exc:
            readability_error = f"readability_unavailable: {str(exc)}"
            logger.warning("readability package unavailable, fallback parser only for url=%s", url)
        except Exception as exc:
            readability_error = f"readability_failed: {str(exc)}"

        fallback_title, fallback_excerpt, thumbnail_url, fallback_html = _extract_fallback_article_html(html, url)

        title = readability_title or fallback_title or "Untitled"
        readability_text = len(re.sub(r"<[^>]+>", "", readability_html or "").strip())
        content_html = readability_html if readability_text > 120 else fallback_html

        if not content_html:
            return {
                "success": False,
                "message": "Không trích xuất được nội dung bài viết từ URL này. Trang có thể chặn bot hoặc cấu trúc HTML không phù hợp.",
                "error_type": "content_extraction_failed",
                "debug": {
                    "url": url,
                    "readability_error": readability_error,
                    "fallback_title": fallback_title,
                    "html_length": len(html or ""),
                },
            }

        blocks, _ = _process_html_to_blocks(content_html, base_url=url)
        if not blocks:
            return {
                "success": False,
                "message": "Đã tải được HTML nhưng không tách được block nội dung để đưa vào editor.",
                "error_type": "block_extraction_failed",
                "debug": {
                    "url": url,
                    "readability_error": readability_error,
                    "content_length": len(content_html or ""),
                },
            }

        title_block = {
            "id": f"block-{int(time.time() * 1000)}-title",
            "type": "heading",
            "x": 40,
            "y": 40,
            "w": 720,
            "h": 90,
            "content": f"<h1>{title}</h1>",
            "props": {
                "fontSize": 32,
                "color": "#0f172a",
                "fontFamily": "Inter, sans-serif",
                "textAlign": "left",
                "fontWeight": "700",
                "lineHeight": 1.25,
            },
        }

        for block in blocks:
            block["y"] += 110

        blocks.insert(0, title_block)

        return {
            "success": True,
            "data": {
                "title": title,
                "excerpt": fallback_excerpt,
                "thumbnail_url": thumbnail_url,
                "blocks": blocks,
            },
            "debug": {
                "url": url,
                "readability_error": readability_error,
                "used_fallback": readability_text <= 120,
            },
        }
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "message": f"Không thể tải URL. HTTP {exc.response.status_code}.",
            "error_type": "http_status_error",
            "debug": {
                "url": url,
                "status_code": exc.response.status_code,
                "response_excerpt": (exc.response.text or "")[:500],
            },
        }
    except httpx.RequestError as exc:
        return {
            "success": False,
            "message": f"Không thể kết nối tới URL: {str(exc)}",
            "error_type": "request_error",
            "debug": {
                "url": url,
                "exception": exc.__class__.__name__,
                "detail": str(exc),
            },
        }
    except Exception as exc:
        trace = traceback.format_exc()
        logger.exception("News crawl failed for url=%s", url)
        return {
            "success": False,
            "message": f"Lỗi backend khi crawl URL: {str(exc)}",
            "error_type": exc.__class__.__name__,
            "debug": {
                "url": url,
                "exception": exc.__class__.__name__,
                "detail": str(exc),
                "traceback": trace[-4000:],
            },
        }
