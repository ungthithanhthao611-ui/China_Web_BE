from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import certifi
import httpx
from bs4 import BeautifulSoup, Tag

from app.utils.news_blocks import normalize_content_json

NOISE_KEYWORDS = (
    "nav",
    "menu",
    "header",
    "footer",
    "sidebar",
    "comment",
    "ads",
    "banner",
    "share",
    "social",
    "related",
    "breadcrumb",
    "newsletter",
    "popup",
    "modal",
)

ALLOWED_BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "blockquote", "figure", "img", "table", "pre", "hr"}
INLINE_TEXT_TAGS = {"p", "ul", "ol", "table", "pre"}


def _strip_noise(soup: BeautifulSoup) -> None:
    for selector in ["script", "style", "noscript", "iframe", "svg", "form", "button", "aside", "footer"]:
        for node in soup.select(selector):
            node.decompose()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _node_identity_tokens(node: Tag) -> str:
    class_tokens = " ".join(node.get("class", [])) if node.has_attr("class") else ""
    return f"{node.name} {node.get('id', '')} {class_tokens}".lower()


def _is_noise_node(node: Tag) -> bool:
    identity = _node_identity_tokens(node)
    return any(token in identity for token in NOISE_KEYWORDS)


def _extract_title(soup: BeautifulSoup) -> str:
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        return str(og_title["content"]).strip()
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(" ", strip=True)
        if text:
            return text
    if soup.title and soup.title.string and soup.title.string.strip():
        return soup.title.string.strip()
    return "Imported reference"


def _extract_excerpt(soup: BeautifulSoup) -> str:
    meta_description = soup.find("meta", attrs={"name": "description"})
    if meta_description and meta_description.get("content"):
        return str(meta_description["content"]).strip()
    og_description = soup.find("meta", attrs={"property": "og:description"})
    if og_description and og_description.get("content"):
        return str(og_description["content"]).strip()
    first_paragraph = soup.find("p")
    if first_paragraph:
        text = first_paragraph.get_text(" ", strip=True)
        if text:
            return text[:260]
    return ""


def _score_candidate(node: Tag) -> float:
    if _is_noise_node(node):
        return -1.0

    paragraphs = node.find_all("p")
    long_paragraphs = []
    paragraph_chars = 0
    for paragraph in paragraphs[:240]:
        text = _clean_text(paragraph.get_text(" ", strip=True))
        if not text:
            continue
        paragraph_chars += len(text)
        if len(text) >= 40:
            long_paragraphs.append(text)

    heading_count = len(node.find_all(["h1", "h2", "h3", "h4"]))
    image_count = len(node.find_all("img"))
    list_count = len(node.find_all(["ul", "ol"]))
    blockquote_count = len(node.find_all("blockquote"))

    if paragraph_chars < 120 and image_count == 0 and heading_count < 1:
        return -1.0

    link_text_chars = 0
    for link in node.find_all("a"):
        link_text_chars += len(_clean_text(link.get_text(" ", strip=True)))

    link_density = link_text_chars / max(paragraph_chars, 1)
    if link_density > 0.85:
        return -1.0

    score = float(paragraph_chars)
    score += len(long_paragraphs) * 120.0
    score += heading_count * 35.0
    score += min(image_count, 12) * 30.0
    score += min(list_count, 12) * 25.0
    score += min(blockquote_count, 6) * 24.0

    if node.name in {"article", "main"}:
        score += 450.0
    if node.name == "section":
        score += 90.0

    if link_density > 0.45:
        score *= 0.55
    elif link_density > 0.3:
        score *= 0.72

    return score


def _find_best_content_root(soup: BeautifulSoup) -> Tag:
    preferred = (
        soup.find("article")
        or soup.find("main")
        or soup.find("section", attrs={"id": "content"})
    )

    best_node = preferred if isinstance(preferred, Tag) else None
    best_score = _score_candidate(best_node) if best_node else -1.0

    for node in soup.find_all(["article", "main", "section", "div"], limit=800):
        if not isinstance(node, Tag):
            continue
        score = _score_candidate(node)
        if score > best_score:
            best_score = score
            best_node = node

    if best_node is not None and best_score > 0:
        return best_node
    return soup.body or soup


def _new_block(block_type: str, y_pos: int, *, content: str = "", props: dict[str, Any] | None = None) -> dict[str, Any]:
    width = 820
    defaults_by_type = {
        "text": {"h": 140, "w": width},
        "heading": {"h": 72, "w": width},
        "image": {"h": 420, "w": width},
        "gallery": {"h": 320, "w": width},
        "quote": {"h": 140, "w": width},
        "divider": {"h": 28, "w": width},
        "two_column": {"h": 240, "w": width},
    }
    sizing = defaults_by_type.get(block_type, {"h": 120, "w": width})
    return {
        "id": f"block-{y_pos}-{block_type}",
        "type": block_type,
        "x": 40,
        "y": y_pos,
        "w": sizing["w"],
        "h": sizing["h"],
        "content": content,
        "props": props or {},
    }


def _normalize_fragment_urls(fragment_html: str, base_url: str) -> str:
    fragment = BeautifulSoup(fragment_html, "html.parser")

    for tag in fragment.find_all(href=True):
        href = str(tag.get("href") or "").strip()
        if not href:
            continue
        tag["href"] = urljoin(base_url, href)
        tag["target"] = "_blank"
        tag["rel"] = "noreferrer noopener"

    for tag in fragment.find_all(src=True):
        src = str(tag.get("src") or "").strip()
        if not src:
            continue
        tag["src"] = urljoin(base_url, src)

    return fragment.decode_contents()


def _extract_image(tag: Tag, base_url: str) -> tuple[str, str]:
    candidates = [
        tag.get("src"),
        tag.get("data-src"),
        tag.get("data-original"),
        tag.get("data-lazy-src"),
    ]
    srcset = str(tag.get("srcset") or tag.get("data-srcset") or "").strip()
    if srcset:
        first_srcset = srcset.split(",")[0].strip().split(" ")[0].strip()
        if first_srcset:
            candidates.append(first_srcset)

    src = ""
    for candidate in candidates:
        value = str(candidate or "").strip()
        if not value:
            continue
        if value.startswith("data:image/"):
            continue
        src = value
        break

    if not src:
        return "", ""

    absolute_src = urljoin(base_url, src)
    alt = _clean_text(str(tag.get("alt") or tag.get("title") or ""))
    return absolute_src, alt


def _estimate_text_block_height(html: str, default: int = 140) -> int:
    text = _clean_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    if not text:
        return default
    estimated = 110 + len(text) // 5
    return max(120, min(540, estimated))


def _normalized_heading_key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _has_block_ancestor(node: Tag, root: Tag) -> bool:
    parent = node.parent
    while isinstance(parent, Tag) and parent is not root:
        if parent.name in ALLOWED_BLOCK_TAGS:
            return True
        parent = parent.parent
    return False


def convert_source_html_to_blocks(html: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    _strip_noise(soup)
    root = _find_best_content_root(soup)

    title = _extract_title(soup)
    excerpt = _extract_excerpt(soup)
    blocks: list[dict[str, Any]] = []
    y_pos = 40
    seen_images: set[str] = set()

    blocks.append(
        _new_block(
            "heading",
            y_pos,
            content=title,
            props={
                "level": "h1",
                "fontFamily": "Georgia, serif",
                "fontSize": 36,
                "fontWeight": 700,
                "color": "#141414",
                "textAlign": "left",
            },
        )
    )
    y_pos += 96

    text_buffer: list[str] = []
    root_title_key = _normalized_heading_key(title)
    seen_heading_keys: set[str] = {root_title_key} if root_title_key else set()

    def flush_text_buffer() -> None:
        nonlocal y_pos
        if not text_buffer:
            return
        merged_html = "".join(text_buffer).strip()
        text_buffer.clear()
        if not merged_html:
            return

        block = _new_block(
            "text",
            y_pos,
            content=merged_html,
            props={
                "fontFamily": "Arial, sans-serif",
                "fontSize": 16,
                "lineHeight": 1.7,
                "color": "#1f2937",
                "textAlign": "justify",
            },
        )
        block["h"] = _estimate_text_block_height(merged_html, 150)
        blocks.append(block)
        y_pos += int(block["h"]) + 18

    candidates = root.find_all(list(ALLOWED_BLOCK_TAGS), recursive=True)
    for node in candidates:
        if not isinstance(node, Tag):
            continue
        if _has_block_ancestor(node, root):
            continue
        if _is_noise_node(node):
            continue

        tag_name = node.name.lower()

        if tag_name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            text = _clean_text(node.get_text(" ", strip=True))
            if not text:
                continue
            heading_key = _normalized_heading_key(text)
            if heading_key in seen_heading_keys:
                continue
            seen_heading_keys.add(heading_key)
            flush_text_buffer()
            level = "h1" if tag_name == "h1" else ("h2" if tag_name in {"h2", "h3"} else "h3")
            heading_size = 32 if level == "h1" else (28 if level == "h2" else 24)
            blocks.append(
                _new_block(
                    "heading",
                    y_pos,
                    content=text,
                    props={
                        "level": level,
                        "fontFamily": "Georgia, serif",
                        "fontSize": heading_size,
                        "fontWeight": 700,
                        "color": "#101828",
                        "textAlign": "left",
                    },
                )
            )
            y_pos += 84
            continue

        if tag_name in INLINE_TEXT_TAGS:
            normalized_html = _normalize_fragment_urls(str(node), source_url).strip()
            text = _clean_text(node.get_text(" ", strip=True))
            if text and normalized_html:
                text_buffer.append(normalized_html)
            continue

        if tag_name == "blockquote":
            quote_text = _clean_text(node.get_text(" ", strip=True))
            if not quote_text:
                continue
            flush_text_buffer()
            blocks.append(
                _new_block(
                    "quote",
                    y_pos,
                    content=f"<p>{quote_text}</p>",
                    props={
                        "fontFamily": "Georgia, serif",
                        "fontSize": 22,
                        "lineHeight": 1.6,
                        "color": "#334155",
                        "textAlign": "left",
                    },
                )
            )
            y_pos += 170
            continue

        if tag_name == "figure":
            images: list[dict[str, Any]] = []
            for image_tag in node.find_all("img"):
                src, alt = _extract_image(image_tag, source_url)
                if not src or src in seen_images:
                    continue
                seen_images.add(src)
                images.append(
                    {
                        "id": f"img-{len(images) + 1}-{y_pos}",
                        "src": src,
                        "alt": alt,
                        "caption": "",
                    }
                )

            if not images:
                continue

            caption = _clean_text(node.find("figcaption").get_text(" ", strip=True) if node.find("figcaption") else "")
            if len(images) == 1:
                flush_text_buffer()
                blocks.append(
                    _new_block(
                        "image",
                        y_pos,
                        props={
                            "src": images[0]["src"],
                            "alt": images[0]["alt"],
                            "caption": caption or images[0]["caption"],
                            "captionText": caption or images[0]["caption"],
                            "captionPosition": "outside-bottom",
                            "borderRadius": 10,
                            "objectFit": "cover",
                            "align": "center",
                            "opacity": 1,
                        },
                    )
                )
                y_pos += 450
                continue

            flush_text_buffer()
            columns = max(2, min(3, len(images)))
            rows = math.ceil(len(images) / columns)
            gallery_height = max(260, min(920, rows * 220 + 20))
            gallery_block = _new_block(
                "gallery",
                y_pos,
                props={
                    "images": images,
                    "columns": columns,
                    "gap": 12,
                    "borderRadius": 8,
                    "objectFit": "cover",
                    "align": "center",
                },
            )
            gallery_block["h"] = gallery_height
            blocks.append(gallery_block)
            y_pos += gallery_height + 20
            continue

        if tag_name == "img":
            src, alt = _extract_image(node, source_url)
            if not src or src in seen_images:
                continue
            flush_text_buffer()
            seen_images.add(src)
            blocks.append(
                _new_block(
                    "image",
                    y_pos,
                    props={
                        "src": src,
                        "alt": alt,
                        "caption": "",
                        "captionText": "",
                        "captionPosition": "outside-bottom",
                        "borderRadius": 10,
                        "objectFit": "cover",
                        "align": "center",
                        "opacity": 1,
                    },
                )
            )
            y_pos += 450
            continue

        if tag_name == "hr":
            flush_text_buffer()
            blocks.append(_new_block("divider", y_pos))
            y_pos += 48

        if len(blocks) >= 160:
            break

    flush_text_buffer()

    if not any(item.get("type") == "text" for item in blocks):
        fallback_text = _clean_text(excerpt or title)
        if fallback_text:
            block = _new_block(
                "text",
                y_pos,
                content=f"<p>{fallback_text}</p>",
                props={
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": 16,
                    "lineHeight": 1.6,
                    "color": "#1f2937",
                    "textAlign": "left",
                },
            )
            block["h"] = _estimate_text_block_height(block["content"], 140)
            blocks.append(block)

    normalized_json = normalize_content_json({"page": {"width": 900, "background": "#ffffff"}, "blocks": blocks})
    raw_text = _clean_text(root.get_text("\n", strip=True) if isinstance(root, Tag) else soup.get_text("\n", strip=True))

    return {
        "title": title,
        "excerpt": excerpt,
        "raw_text": raw_text[:120000],
        "parsed_json": normalized_json,
    }


async def fetch_source_and_parse(url: str) -> dict[str, Any]:
    timeout = httpx.Timeout(20.0, connect=8.0)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; NewsWorkflowBot/1.0)",
        "Accept-Language": "en,vi;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=certifi.where()) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text
    except Exception:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text

    parsed = convert_source_html_to_blocks(html, url)
    return {
        "source_url": url,
        "hostname": urlparse(url).hostname or "",
        "raw_html": html[:600000],
        **parsed,
    }
