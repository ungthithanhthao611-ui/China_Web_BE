from __future__ import annotations

import re

from bs4 import BeautifulSoup

ALLOWED_TAGS = {
    "article",
    "section",
    "div",
    "span",
    "p",
    "br",
    "strong",
    "em",
    "u",
    "s",
    "b",
    "i",
    "ul",
    "ol",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "blockquote",
    "figure",
    "figcaption",
    "img",
    "hr",
    "a",
}

ALLOWED_STYLE_PROPERTIES = {
    "color",
    "background-color",
    "font-family",
    "font-size",
    "font-weight",
    "font-style",
    "line-height",
    "text-align",
    "text-decoration",
    "text-indent",
    "padding",
    "margin",
    "border-radius",
    "object-fit",
    "opacity",
    "width",
    "height",
    "gap",
    "display",
    "grid-template-columns",
}

SAFE_URL_RE = re.compile(r"^(https?://|/|#)", re.IGNORECASE)
SAFE_CSS_VALUE_RE = re.compile(r"^[#(),.%\s\-\w\"']+$")


def _sanitize_style(value: str | None) -> str:
    if not value:
        return ""
    declarations: list[str] = []
    for declaration in str(value).split(";"):
        if ":" not in declaration:
            continue
        key, raw_value = declaration.split(":", 1)
        css_key = key.strip().lower()
        css_value = raw_value.strip()
        if css_key not in ALLOWED_STYLE_PROPERTIES:
            continue
        if not SAFE_CSS_VALUE_RE.match(css_value):
            continue
        declarations.append(f"{css_key}: {css_value}")
    return "; ".join(declarations)


def sanitize_html(html: str | None) -> str:
    soup = BeautifulSoup(str(html or ""), "html.parser")

    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
            continue

        attrs_to_delete: list[str] = []
        for attr_name, attr_value in list(tag.attrs.items()):
            normalized_attr = str(attr_name).lower()
            if normalized_attr.startswith("on"):
                attrs_to_delete.append(attr_name)
                continue

            if normalized_attr == "style":
                clean_style = _sanitize_style(str(attr_value))
                if clean_style:
                    tag.attrs[attr_name] = clean_style
                else:
                    attrs_to_delete.append(attr_name)
                continue

            if normalized_attr in {"class", "id", "data-id"}:
                continue

            if tag.name == "a" and normalized_attr == "href":
                href = str(attr_value).strip()
                if SAFE_URL_RE.match(href):
                    tag.attrs[attr_name] = href
                else:
                    attrs_to_delete.append(attr_name)
                continue

            if tag.name == "a" and normalized_attr in {"target", "rel"}:
                continue

            if tag.name == "img" and normalized_attr in {"src", "alt", "title", "width", "height"}:
                if normalized_attr == "src":
                    src = str(attr_value).strip()
                    if not SAFE_URL_RE.match(src):
                        attrs_to_delete.append(attr_name)
                continue

            attrs_to_delete.append(attr_name)

        for attr_name in attrs_to_delete:
            tag.attrs.pop(attr_name, None)

    return str(soup)

