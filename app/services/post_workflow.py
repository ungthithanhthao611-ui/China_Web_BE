from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import certifi
import httpx
import markdown
from bs4 import BeautifulSoup
from fastapi import HTTPException, UploadFile, status
from pypdf import PdfReader
from docx import Document

from app.schemas.post_workflow import (
    ImportedFileMeta,
    PostImportPreview,
    PostSourceFetchRequest,
    PostSourcePreview,
    PostWorkflowDraft,
)

SUPPORTED_IMPORT_EXTENSIONS = {'.docx', '.txt', '.md', '.html', '.htm', '.pdf'}
SUPPORTED_IMPORT_MIME_TYPES = {
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'text/markdown',
    'text/html',
    'application/pdf',
}

PUBLIC_NEWS_CATEGORIES = {
    'corporate-news': {
        'label': 'Corporate News',
        'keywords': {
            'corporate', 'company', 'enterprise', 'branch', 'subsidiary', 'chairman', 'leadership',
            'milestone', 'anniversary', 'launch', 'cooperation', 'signed', 'award', 'event',
            'opening', 'ceremony', 'project update', 'partnership', 'headquarters', 'team',
        },
        'url_keywords': {'corporate', 'company', 'enterprise', 'news_detail', 'news-detail', 'group', 'branch'},
    },
    'industry-dynamics': {
        'label': 'Industry dynamics',
        'keywords': {
            'industry', 'market', 'trend', 'policy', 'economy', 'construction sector', 'analysis',
            'green building', 'smart building', 'regulation', 'forum', 'conference', 'supply chain',
            'innovation', 'technology', 'research', 'development', 'outlook', 'report',
        },
        'url_keywords': {'industry', 'dynamic', 'dynamics', 'trend', 'market', 'policy', 'analysis', 'news_detail2'},
    },
    'needs-review': {
        'label': 'Needs Review',
        'keywords': set(),
        'url_keywords': set(),
    },
}


def slugify(value: str) -> str:
    normalized = (value or '').strip().lower()
    replacements = {
        'à': 'a',
        'á': 'a',
        'ạ': 'a',
        'ả': 'a',
        'ã': 'a',
        'â': 'a',
        'ầ': 'a',
        'ấ': 'a',
        'ậ': 'a',
        'ẩ': 'a',
        'ẫ': 'a',
        'ă': 'a',
        'ằ': 'a',
        'ắ': 'a',
        'ặ': 'a',
        'ẳ': 'a',
        'ẵ': 'a',
        'è': 'e',
        'é': 'e',
        'ẹ': 'e',
        'ẻ': 'e',
        'ẽ': 'e',
        'ê': 'e',
        'ề': 'e',
        'ế': 'e',
        'ệ': 'e',
        'ể': 'e',
        'ễ': 'e',
        'ì': 'i',
        'í': 'i',
        'ị': 'i',
        'ỉ': 'i',
        'ĩ': 'i',
        'ò': 'o',
        'ó': 'o',
        'ọ': 'o',
        'ỏ': 'o',
        'õ': 'o',
        'ô': 'o',
        'ồ': 'o',
        'ố': 'o',
        'ộ': 'o',
        'ổ': 'o',
        'ỗ': 'o',
        'ơ': 'o',
        'ờ': 'o',
        'ớ': 'o',
        'ợ': 'o',
        'ở': 'o',
        'ỡ': 'o',
        'ù': 'u',
        'ú': 'u',
        'ụ': 'u',
        'ủ': 'u',
        'ũ': 'u',
        'ư': 'u',
        'ừ': 'u',
        'ứ': 'u',
        'ự': 'u',
        'ử': 'u',
        'ữ': 'u',
        'ỳ': 'y',
        'ý': 'y',
        'ỵ': 'y',
        'ỷ': 'y',
        'ỹ': 'y',
        'đ': 'd',
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)

    chunks: list[str] = []
    current = []
    for character in normalized:
        if character.isalnum():
            current.append(character)
        else:
            if current:
                chunks.append(''.join(current))
                current = []
    if current:
        chunks.append(''.join(current))
    return '-'.join(chunks)


def summarize_text(text: str, limit: int = 220) -> str:
    normalized = ' '.join((text or '').split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def paragraphs_to_html(text: str) -> str:
    paragraphs = [segment.strip() for segment in (text or '').split('\n\n') if segment.strip()]
    if not paragraphs:
        return '<p></p>'
    return ''.join(f'<p>{paragraph.replace(chr(10), "<br/>")}</p>' for paragraph in paragraphs)


def build_reference_draft(title: str, summary: str, body_html: str, url: str, note: str | None = None) -> PostWorkflowDraft:
    editorial_note = note or 'Biên tập lại nội dung theo góc nhìn riêng, kiểm chứng dữ kiện và không sao chép nguyên văn.'
    composed_html = (
        '<h2>Ghi chú biên tập từ nguồn tham khảo</h2>'
        f'<p><strong>Nguồn:</strong> <a href="{url}" target="_blank" rel="noreferrer noopener">{url}</a></p>'
        f'<p><strong>Định hướng:</strong> {editorial_note}</p>'
        f'<hr/>{body_html}'
    )
    return PostWorkflowDraft(
        title=title,
        slug=slugify(title),
        summary=summary,
        body=composed_html,
        meta_title=title,
        meta_description=summarize_text(summary or title, 160),
        author=None,
    )


def normalize_fragment_urls(fragment_html: str, base_url: str) -> str:
    fragment = BeautifulSoup(fragment_html, 'html.parser')

    for tag in fragment.find_all(href=True):
        href = (tag.get('href') or '').strip()
        if href:
            tag['href'] = urljoin(base_url, href)
            tag['target'] = '_blank'
            tag['rel'] = 'noreferrer noopener'

    for tag in fragment.find_all(src=True):
        src = (tag.get('src') or '').strip()
        if src:
            tag['src'] = urljoin(base_url, src)

    return ''.join(str(node) for node in fragment.contents)


def build_article_html(article: BeautifulSoup, base_url: str) -> str:
    allowed_tags = ['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'blockquote', 'figure', 'img', 'table']
    segments: list[str] = []
    seen_segments: set[str] = set()
    seen_image_sources: set[str] = set()

    for node in article.find_all(allowed_tags, limit=240):
        if node.name == 'img' and node.find_parent(['figure', 'picture']):
            continue

        has_meaningful_text = bool(node.get_text(' ', strip=True))
        has_media = node.name in {'figure', 'img', 'table'} or bool(node.find(['img', 'table']))
        if not has_meaningful_text and not has_media:
            continue

        normalized_html = normalize_fragment_urls(str(node), base_url).strip()
        if not normalized_html:
            continue

        if node.name == 'img':
            image_src = (node.get('src') or '').strip()
            normalized_src = urljoin(base_url, image_src) if image_src else ''
            if normalized_src and normalized_src in seen_image_sources:
                continue
            if normalized_src:
                seen_image_sources.add(normalized_src)

        if node.name == 'figure':
            figure_images = [urljoin(base_url, (img.get('src') or '').strip()) for img in node.find_all('img') if (img.get('src') or '').strip()]
            if figure_images and all(image_src in seen_image_sources for image_src in figure_images):
                continue
            for image_src in figure_images:
                seen_image_sources.add(image_src)

        if normalized_html in seen_segments:
            continue

        seen_segments.add(normalized_html)
        segments.append(normalized_html)

    return ''.join(segments)


def is_ssl_verification_error(exc: Exception) -> bool:
    message = str(exc or '')
    return 'CERTIFICATE_VERIFY_FAILED' in message or 'certificate verify failed' in message.lower()


def suggest_post_category(url: str | None = None, title: str | None = None, plain_text: str | None = None) -> dict[str, str | float | None]:
    combined_text = ' '.join(part for part in [title or '', plain_text or ''] if part).lower()
    normalized_url = (url or '').lower()
    category_scores: dict[str, float] = {slug: 0.0 for slug in PUBLIC_NEWS_CATEGORIES}
    matched_reasons: dict[str, list[str]] = {slug: [] for slug in PUBLIC_NEWS_CATEGORIES}

    for slug, config in PUBLIC_NEWS_CATEGORIES.items():
        for keyword in config['url_keywords']:
            if keyword in normalized_url:
                category_scores[slug] += 3
                matched_reasons[slug].append(f'URL: {keyword}')

        for keyword in config['keywords']:
            if keyword in combined_text:
                category_scores[slug] += 1.5 if ' ' in keyword else 1
                matched_reasons[slug].append(f'Keyword: {keyword}')

    best_slug = max(category_scores, key=category_scores.get)
    best_score = category_scores[best_slug]
    other_score = max(score for slug, score in category_scores.items() if slug != best_slug)

    if best_score <= 0:
        return {
            'suggested_category_slug': 'needs-review',
            'suggested_category_label': 'Needs Review',
            'category_confidence': 0.0,
            'category_reason': 'Không tìm thấy tín hiệu đủ mạnh từ URL, tiêu đề hoặc nội dung.',
        }

    confidence = min(0.98, round(0.55 + (best_score - other_score) * 0.08 + min(best_score, 6) * 0.03, 2))
    if best_score - other_score < 1:
        return {
            'suggested_category_slug': 'needs-review',
            'suggested_category_label': 'Needs Review',
            'category_confidence': round(max(0.35, confidence - 0.25), 2),
            'category_reason': 'Tín hiệu phân loại chưa đủ chắc chắn, cần editor xác nhận lại.',
        }

    reasons = ', '.join(matched_reasons[best_slug][:4]) or 'Matched source signals'
    return {
        'suggested_category_slug': best_slug,
        'suggested_category_label': PUBLIC_NEWS_CATEGORIES[best_slug]['label'],
        'category_confidence': confidence,
        'category_reason': reasons,
    }


async def fetch_remote_html(url: str, timeout: httpx.Timeout) -> str:
    request_headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; ChinaCMSBot/1.0; +https://localhost)',
        'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8',
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=certifi.where()) as client:
            response = await client.get(url, headers=request_headers)
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as exc:
        if not is_ssl_verification_error(exc):
            raise

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
            response = await client.get(url, headers=request_headers)
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Không thể tải nội dung nguồn tham khảo: {exc}',
        ) from exc


async def fetch_post_source_preview(payload: PostSourceFetchRequest) -> PostSourcePreview:
    url = str(payload.url)
    timeout = httpx.Timeout(20.0, connect=10.0)

    try:
        response_text = await fetch_remote_html(url, timeout)
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Không thể tải nội dung nguồn tham khảo: {exc}',
        ) from exc

    soup = BeautifulSoup(response_text, 'html.parser')

    for selector in ['script', 'style', 'noscript', 'iframe', 'svg']:
        for node in soup.select(selector):
            node.decompose()

    title = (
        (soup.title.string.strip() if soup.title and soup.title.string else None)
        or (soup.find('meta', attrs={'property': 'og:title'}) or {}).get('content')
        or (soup.find('h1').get_text(' ', strip=True) if soup.find('h1') else None)
        or payload.source_name
        or 'Bản tham khảo mới'
    )

    excerpt = (
        (soup.find('meta', attrs={'name': 'description'}) or {}).get('content')
        or (soup.find('meta', attrs={'property': 'og:description'}) or {}).get('content')
    )

    article = soup.find('article') or soup.find('main') or soup.body or soup
    paragraphs = [node.get_text(' ', strip=True) for node in article.find_all(['p', 'li', 'h1', 'h2', 'h3', 'h4'])]
    plain_text = '\n\n'.join(segment for segment in paragraphs if segment)
    trimmed_text = plain_text[:50000]
    summary = summarize_text(excerpt or trimmed_text or title, 240)

    body_html = build_article_html(article, url) or paragraphs_to_html(trimmed_text)

    draft = build_reference_draft(title=title, summary=summary, body_html=body_html, url=url, note=payload.note)
    hostname = urlparse(url).hostname or ''
    category_suggestion = suggest_post_category(url=url, title=title, plain_text=trimmed_text)

    return PostSourcePreview(
        url=url,
        hostname=hostname,
        source_name=payload.source_name,
        title=title,
        excerpt=summary,
        plain_text=trimmed_text,
        html=body_html,
        source_label='reference',
        readability_score=min(100, max(25, len(trimmed_text.split()) // 8 if trimmed_text else 25)),
        note=payload.note,
        draft=draft,
        suggested_category_slug=category_suggestion['suggested_category_slug'],
        suggested_category_label=category_suggestion['suggested_category_label'],
        category_confidence=category_suggestion['category_confidence'],
        category_reason=category_suggestion['category_reason'],
    )


def _read_docx(file_bytes: bytes) -> str:
    document = Document(BytesIO(file_bytes))
    return '\n\n'.join(paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip())


def _read_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        extracted = (page.extract_text() or '').strip()
        if extracted:
            pages.append(extracted)
    return '\n\n'.join(pages)


def _detect_format(suffix: str, mime_type: str | None) -> str:
    normalized_suffix = suffix.lower()
    if normalized_suffix == '.docx':
        return 'docx'
    if normalized_suffix == '.pdf' or mime_type == 'application/pdf':
        return 'pdf'
    if normalized_suffix in {'.html', '.htm'}:
        return 'html'
    if normalized_suffix == '.md' or mime_type == 'text/markdown':
        return 'markdown'
    return 'text'


async def import_post_file_preview(file: UploadFile) -> PostImportPreview:
    suffix = Path(file.filename or '').suffix.lower()
    mime_type = file.content_type

    if suffix not in SUPPORTED_IMPORT_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Định dạng file chưa được hỗ trợ. Hãy dùng docx, txt, md, html hoặc pdf.',
        )

    if mime_type and mime_type not in SUPPORTED_IMPORT_MIME_TYPES and not mime_type.startswith('text/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='MIME type của file không hợp lệ cho workflow import.',
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='File import đang trống.')

    detected_format = _detect_format(suffix, mime_type)
    raw_text = ''
    html = ''

    if detected_format == 'docx':
        raw_text = _read_docx(file_bytes)
        html = paragraphs_to_html(raw_text)
    elif detected_format == 'pdf':
        raw_text = _read_pdf(file_bytes)
        html = paragraphs_to_html(raw_text)
    elif detected_format == 'html':
        html = file_bytes.decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
        raw_text = soup.get_text('\n', strip=True)
    elif detected_format == 'markdown':
        raw_text = file_bytes.decode('utf-8', errors='ignore')
        html = markdown.markdown(raw_text, extensions=['tables', 'sane_lists'])
    else:
        raw_text = file_bytes.decode('utf-8', errors='ignore')
        html = paragraphs_to_html(raw_text)

    base_title = Path(file.filename or 'bai-viet-moi').stem.replace('_', ' ').replace('-', ' ').strip() or 'Bài viết mới'
    summary = summarize_text(raw_text or BeautifulSoup(html, 'html.parser').get_text(' ', strip=True), 240)
    draft = PostWorkflowDraft(
        title=base_title,
        slug=slugify(base_title),
        summary=summary,
        body=html,
        meta_title=base_title,
        meta_description=summarize_text(summary or base_title, 160),
        author=None,
    )

    category_suggestion = suggest_post_category(title=base_title, plain_text=raw_text or summary)

    return PostImportPreview(
        file=ImportedFileMeta(
            file_name=file.filename or 'unknown',
            mime_type=mime_type,
            extension=suffix or None,
            detected_format=detected_format,
            character_count=len((raw_text or '').strip()),
        ),
        title=base_title,
        summary=summary,
        body=html,
        plain_text=raw_text or BeautifulSoup(html, 'html.parser').get_text(' ', strip=True),
        draft=draft,
        suggested_category_slug=category_suggestion['suggested_category_slug'],
        suggested_category_label=category_suggestion['suggested_category_label'],
        category_confidence=category_suggestion['category_confidence'],
        category_reason=category_suggestion['category_reason'],
    )
