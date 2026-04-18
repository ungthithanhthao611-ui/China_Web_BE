from __future__ import annotations

from typing import Any

from app.utils.html_sanitizer import sanitize_html

SUPPORTED_BLOCK_TYPES = {"text", "heading", "image", "gallery", "quote", "divider", "two_column"}


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_content_json(content_json: dict | None) -> dict[str, Any]:
    raw = content_json or {}
    raw_page = raw.get("page") or {}
    page = {
        "width": max(600, min(1600, _to_int(raw_page.get("width"), 900))),
        "background": str(raw_page.get("background") or "#ffffff"),
    }

    normalized_blocks: list[dict[str, Any]] = []
    raw_blocks = raw.get("blocks") or []
    for index, item in enumerate(raw_blocks):
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("type") or "").strip().lower()
        if block_type not in SUPPORTED_BLOCK_TYPES:
            continue

        block = {
            "id": str(item.get("id") or f"block-{index + 1}"),
            "type": block_type,
            "x": _to_int(item.get("x"), 40),
            "y": _to_int(item.get("y"), 40 + index * 140),
            "w": max(80, _to_int(item.get("w"), 720)),
            "h": max(36, _to_int(item.get("h"), 120)),
            "content": str(item.get("content") or ""),
            "props": item.get("props") if isinstance(item.get("props"), dict) else {},
        }

        if block_type == "gallery":
            props = block["props"]
            raw_images = props.get("images") if isinstance(props.get("images"), list) else []
            if not raw_images and isinstance(props.get("items"), list):
                raw_images = props.get("items") or []
            normalized_images: list[dict[str, str]] = []
            for image_index, raw_image in enumerate(raw_images):
                if not isinstance(raw_image, dict):
                    continue
                normalized_images.append(
                    {
                        "id": str(raw_image.get("id") or f"img-{image_index + 1}"),
                        "src": str(raw_image.get("src") or ""),
                        "alt": str(raw_image.get("alt") or ""),
                        "caption": str(raw_image.get("caption") or ""),
                    }
                )
            props["images"] = normalized_images
            if "items" in props:
                del props["items"]

        normalized_blocks.append(block)

    return {"page": page, "blocks": normalized_blocks}


def _build_inline_style(props: dict[str, Any]) -> str:
    pairs: list[str] = []
    mapping = {
        "fontFamily": "font-family",
        "fontSize": "font-size",
        "fontWeight": "font-weight",
        "fontStyle": "font-style",
        "color": "color",
        "backgroundColor": "background-color",
        "lineHeight": "line-height",
        "textAlign": "text-align",
        "textDecoration": "text-decoration",
        "textIndent": "text-indent",
        "opacity": "opacity",
        "objectFit": "object-fit",
        "borderRadius": "border-radius",
    }

    for source_key, target_key in mapping.items():
        value = props.get(source_key)
        if value in (None, ""):
            continue
        if source_key in {"fontSize", "borderRadius"}:
            pairs.append(f"{target_key}: {_to_int(value, 0)}px")
            continue
        pairs.append(f"{target_key}: {value}")

    width = props.get("width")
    height = props.get("height")
    if width not in (None, ""):
        pairs.append(f"width: {_to_int(width, 0)}px")
    if height not in (None, ""):
        pairs.append(f"height: {_to_int(height, 0)}px")

    return "; ".join(pairs)


def render_content_json_to_html(content_json: dict | None) -> str:
    normalized = normalize_content_json(content_json)
    blocks = sorted(normalized["blocks"], key=lambda item: (item.get("y", 0), item.get("x", 0)))

    fragments: list[str] = ['<article class="news-workflow-content">']
    for block in blocks:
        block_type = block["type"]
        props = block.get("props") or {}
        style = _build_inline_style(props)
        style_attr = f' style="{style}"' if style else ""

        if block_type == "text":
            fragments.append(f'<section class="news-block news-block-text"{style_attr}>{block.get("content", "")}</section>')
            continue

        if block_type == "heading":
            level = str(props.get("level") or "h2").lower()
            heading_tag = level if level in {"h1", "h2", "h3"} else "h2"
            fragments.append(f'<{heading_tag} class="news-block news-block-heading"{style_attr}>{block.get("content", "")}</{heading_tag}>')
            continue

        if block_type == "image":
            src = str(props.get("src") or "").strip()
            alt = str(props.get("alt") or "")
            caption = str(props.get("caption") or props.get("captionText") or "")
            if not src:
                continue
            align = str(props.get("align") or "left")
            fragments.append(f'<figure class="news-block news-block-image align-{align}"{style_attr}>')
            fragments.append(f'<img src="{src}" alt="{alt}" />')
            if caption:
                fragments.append(f"<figcaption>{caption}</figcaption>")
            fragments.append("</figure>")
            continue

        if block_type == "gallery":
            raw_images = props.get("images") if isinstance(props.get("images"), list) else []
            if not raw_images and isinstance(props.get("items"), list):
                raw_images = props.get("items") or []
            images: list[dict[str, str]] = []
            for raw_image in raw_images:
                if not isinstance(raw_image, dict):
                    continue
                src = str(raw_image.get("src") or "").strip()
                if not src:
                    continue
                images.append(
                    {
                        "src": src,
                        "alt": str(raw_image.get("alt") or ""),
                        "caption": str(raw_image.get("caption") or ""),
                    }
                )

            if not images:
                continue

            columns = max(1, min(6, _to_int(props.get("columns"), 3)))
            gap = max(0, _to_int(props.get("gap"), 12))
            border_radius = max(0, _to_int(props.get("borderRadius"), 8))
            object_fit = str(props.get("objectFit") or "cover")
            align = str(props.get("align") or "center")
            fragments.append(
                f'<section class="news-block news-block-gallery align-{align}" '
                f'style="display:grid; grid-template-columns:repeat({columns}, minmax(0,1fr)); gap:{gap}px;">'
            )
            for item in images:
                fragments.append('<figure class="gallery-item">')
                fragments.append(
                    f'<img src="{item["src"]}" alt="{item["alt"]}" '
                    f'style="width:100%; height:100%; object-fit:{object_fit}; border-radius:{border_radius}px;" />'
                )
                if item["caption"]:
                    fragments.append(f"<figcaption>{item['caption']}</figcaption>")
                fragments.append("</figure>")
            fragments.append("</section>")
            continue

        if block_type == "quote":
            fragments.append(f'<blockquote class="news-block news-block-quote"{style_attr}>{block.get("content", "")}</blockquote>')
            continue

        if block_type == "divider":
            fragments.append('<hr class="news-block news-block-divider" />')
            continue

        if block_type == "two_column":
            left_content = str(props.get("leftContent") or "")
            right_content = str(props.get("rightContent") or "")
            gap = max(0, _to_int(props.get("gap"), 24))
            fragments.append(f'<section class="news-block news-block-two-column" style="display:grid; grid-template-columns:1fr 1fr; gap:{gap}px;">')
            fragments.append(f'<div class="two-column-item"{style_attr}>{left_content}</div>')
            fragments.append(f'<div class="two-column-item"{style_attr}>{right_content}</div>')
            fragments.append("</section>")

    fragments.append("</article>")
    return sanitize_html("".join(fragments))


def has_publishable_content(content_json: dict | None) -> bool:
    normalized = normalize_content_json(content_json)
    for block in normalized["blocks"]:
        block_type = block.get("type")
        content = str(block.get("content") or "").strip()
        props = block.get("props") or {}
        if block_type in {"text", "heading", "quote"} and content:
            return True
        if block_type == "image" and str(props.get("src") or "").strip():
            return True
        if block_type == "gallery":
            images = props.get("images") if isinstance(props.get("images"), list) else []
            if not images and isinstance(props.get("items"), list):
                images = props.get("items") or []
            if any(isinstance(item, dict) and str(item.get("src") or "").strip() for item in images):
                return True
        if block_type == "two_column":
            if str(props.get("leftContent") or "").strip() or str(props.get("rightContent") or "").strip():
                return True
    return False


def estimate_text_score(content_json: dict | None) -> int:
    normalized = normalize_content_json(content_json)
    score = 0
    for block in normalized["blocks"]:
        content = str(block.get("content") or "")
        props = block.get("props") or {}
        score += len(content.strip())
        score += len(str(props.get("leftContent") or "").strip())
        score += len(str(props.get("rightContent") or "").strip())
        if block.get("type") == "gallery":
            images = props.get("images") if isinstance(props.get("images"), list) else []
            if not images and isinstance(props.get("items"), list):
                images = props.get("items") or []
            for item in images:
                if not isinstance(item, dict):
                    continue
                score += len(str(item.get("caption") or "").strip())
                score += len(str(item.get("alt") or "").strip())
    return score
