from __future__ import annotations

import argparse
import html
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import cloudinary
import cloudinary.uploader
import requests
import urllib3

SOURCE_PAGE_URL = 'https://en.sinodecor.com/video.html'
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
VIDEO_BLOCK_PATTERN = re.compile(
    r'<div class="cbox-34 p_loopitem.*?>.*?'
    r'<img src="(?P<thumbnail>[^"]+)" alt="(?P<image_alt>[^"]*)" title="(?P<image_title>[^"]*)".*?'
    r'<p class="e_text-39 s_title fnt_18">\s*(?P<title>.*?)\s*</p>.*?'
    r'<div class="add_video_data" data-ovide="(?P<data_video>[^"]+)" data-otime="(?P<duration>\d+)"></div>.*?'
    r'<video class="video" src="(?P<video_src>[^"]+)"',
    re.S,
)


class AdminImporter:
    def __init__(self, api_base: str, username: str, password: str, timeout: int = 120) -> None:
        self.api_base = api_base.rstrip('/')
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = False
        self.token: str | None = None

    def _url(self, path: str) -> str:
        return f'{self.api_base}{path}'

    def login(self) -> None:
        response = self.session.post(
            self._url('/auth/login'),
            json={'username': self.username, 'password': self.password},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        self.token = payload['access_token']
        self.session.headers.update({'Authorization': f'Bearer {self.token}'})

    def list_entity(self, entity_name: str, **query: Any) -> dict[str, Any]:
        response = self.session.get(
            self._url(f'/admin/{entity_name}'),
            params=query,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def create_entity(self, entity_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            self._url(f'/admin/{entity_name}'),
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def update_entity(self, entity_name: str, record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.put(
            self._url(f'/admin/{entity_name}/{record_id}'),
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def upload_media(
        self,
        file_path: Path,
        title: str,
        alt_text: str,
        *,
        asset_folder: str | None = None,
        public_id_base: str | None = None,
    ) -> dict[str, Any]:
        mime_type = mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'
        with file_path.open('rb') as file_handle:
            response = self.session.post(
                self._url('/admin/media/upload'),
                data={
                    'title': title,
                    'alt_text': alt_text,
                    'asset_folder': asset_folder or '',
                    'public_id_base': public_id_base or '',
                },
                files={
                    'file': (file_path.name, file_handle, mime_type),
                },
                timeout=self.timeout,
            )
        response.raise_for_status()
        return response.json()


def load_backend_env() -> dict[str, str]:
    env_path = Path(__file__).resolve().parent.parent / '.env'
    values: dict[str, str] = {}

    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


class CloudinaryVideoUploader:
    def __init__(self) -> None:
        env_values = load_backend_env()
        cloud_name = (os.getenv('CLOUDINARY_CLOUD_NAME') or env_values.get('CLOUDINARY_CLOUD_NAME') or '').strip()
        api_key = (os.getenv('CLOUDINARY_API_KEY') or env_values.get('CLOUDINARY_API_KEY') or '').strip()
        api_secret = (os.getenv('CLOUDINARY_API_SECRET') or env_values.get('CLOUDINARY_API_SECRET') or '').strip()
        folder = (os.getenv('CLOUDINARY_FOLDER') or env_values.get('CLOUDINARY_FOLDER') or 'China_web').strip() or 'China_web'

        if not all([cloud_name, api_key, api_secret]):
            raise RuntimeError('Thiếu cấu hình Cloudinary trong biến môi trường.')

        self.folder = folder
        self.video_folder = f'{folder}/videos'
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )

    def build_public_id(self, title: str) -> str:
        return slugify(title)

    def _upload_kwargs(self, title: str) -> dict[str, Any]:
        return {
            'resource_type': 'video',
            'public_id': self.build_public_id(title),
            'asset_folder': self.video_folder,
            'use_asset_folder_as_public_id_prefix': True,
            'overwrite': True,
            'invalidate': True,
            'use_filename': False,
            'unique_filename': False,
            'display_name': title,
        }

    def _normalize_result(self, result: dict[str, Any], fallback_url: str, public_id: str) -> dict[str, Any]:
        return {
            'url': result.get('secure_url') or result.get('url') or fallback_url,
            'storage_backend': 'cloudinary',
            'public_id': result.get('public_id') or public_id,
        }

    def upload_remote_video(self, video_url: str, title: str) -> dict[str, Any]:
        upload_kwargs = self._upload_kwargs(title)
        public_id = f"{self.video_folder}/{upload_kwargs['public_id']}"
        result = cloudinary.uploader.upload(
            video_url,
            **upload_kwargs,
        )
        return self._normalize_result(result, video_url, public_id)

    def upload_local_video(self, file_path: Path, title: str, fallback_url: str) -> dict[str, Any]:
        upload_kwargs = self._upload_kwargs(title)
        public_id = f"{self.video_folder}/{upload_kwargs['public_id']}"
        result = cloudinary.uploader.upload_large(
            str(file_path),
            **upload_kwargs,
        )
        return self._normalize_result(result, fallback_url, public_id)


def normalize_space(value: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(value or '')).strip()


def slugify(value: str) -> str:
    normalized = normalize_space(value).lower()
    normalized = re.sub(r'[^a-z0-9]+', '-', normalized)
    normalized = re.sub(r'-+', '-', normalized).strip('-')
    return normalized or 'video'


def crawl_source_videos(source_page_url: str = SOURCE_PAGE_URL) -> list[dict[str, Any]]:
    response = requests.get(source_page_url, timeout=60, verify=False)
    response.raise_for_status()
    html_text = response.text

    results: list[dict[str, Any]] = []
    for index, match in enumerate(VIDEO_BLOCK_PATTERN.finditer(html_text), start=1):
        title = normalize_space(match.group('title'))
        thumbnail_url = urljoin(source_page_url, match.group('thumbnail'))
        raw_video_url = match.group('video_src') or match.group('data_video')
        video_url = urljoin(source_page_url, raw_video_url)
        duration_seconds = int(match.group('duration'))

        results.append(
            {
                'title': title,
                'description': f'{title} - imported from en.sinodecor.com video gallery.',
                'thumbnail_url': thumbnail_url,
                'video_url': video_url,
                'duration_seconds': duration_seconds,
                'sort_order': index,
                'status': 'published',
            }
        )

    if not results:
        raise RuntimeError('Không crawl được video nào từ trang nguồn.')

    return results


def download_to_temp(url: str, suffix: str) -> Path:
    response = requests.get(url, timeout=180, stream=True, verify=False)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                temp_file.write(chunk)
        return Path(temp_file.name)


def get_language_id(importer: AdminImporter, language_code: str) -> int:
    response = importer.list_entity('languages', limit=100)
    items = response.get('items') or []
    for item in items:
        if StringHelper.lower(item.get('code')) == language_code.lower():
            return int(item['id'])

    if items:
        return int(items[0]['id'])

    raise RuntimeError('Không tìm thấy language nào trong admin.')


class StringHelper:
    @staticmethod
    def lower(value: Any) -> str:
        return str(value or '').strip().lower()


def get_existing_videos(importer: AdminImporter) -> dict[str, dict[str, Any]]:
    response = importer.list_entity('videos', limit=100)
    items = response.get('items') or []
    return {StringHelper.lower(item.get('title')): item for item in items}


def import_videos(
    importer: AdminImporter,
    videos: list[dict[str, Any]],
    language_id: int,
    upload_videos_to_cloudinary: bool,
    use_remote_cloudinary_upload: bool,
) -> list[dict[str, Any]]:
    existing_by_title = get_existing_videos(importer)
    results: list[dict[str, Any]] = []
    video_uploader = None

    if upload_videos_to_cloudinary and use_remote_cloudinary_upload:
        video_uploader = CloudinaryVideoUploader()

    for item in videos:
        title = item['title']
        title_key = StringHelper.lower(title)
        thumbnail_path: Path | None = None
        video_path: Path | None = None

        try:
            thumbnail_suffix = Path(item['thumbnail_url']).suffix or '.jpg'
            thumbnail_path = download_to_temp(item['thumbnail_url'], thumbnail_suffix)
            thumbnail_media = importer.upload_media(
                thumbnail_path,
                title=f'{title} Thumbnail',
                alt_text=title,
                asset_folder='videos',
                public_id_base=f'{slugify(title)}-thumbnail',
            )
            thumbnail_id = thumbnail_media['id']
            thumbnail_backend = thumbnail_media.get('storage_backend', 'unknown')

            final_video_url = item['video_url']
            video_backend = 'source'
            video_error = ''

            if upload_videos_to_cloudinary:
                try:
                    if video_uploader:
                        try:
                            video_media = video_uploader.upload_remote_video(item['video_url'], title)
                        except Exception:
                            video_suffix = Path(item['video_url']).suffix or '.mp4'
                            video_path = download_to_temp(item['video_url'], video_suffix)
                            video_media = video_uploader.upload_local_video(video_path, title, item['video_url'])
                    else:
                        video_suffix = Path(item['video_url']).suffix or '.mp4'
                        video_path = download_to_temp(item['video_url'], video_suffix)
                        video_media = importer.upload_media(
                            video_path,
                            title=title,
                            alt_text=title,
                            asset_folder='videos',
                            public_id_base=slugify(title),
                        )
                    final_video_url = video_media['url']
                    video_backend = video_media.get('storage_backend', 'unknown')
                except Exception as exc:  # noqa: BLE001
                    video_error = str(exc)
                    video_backend = 'source-fallback'

            payload = {
                'title': title,
                'description': item['description'],
                'video_url': final_video_url,
                'thumbnail_id': thumbnail_id,
                'language_id': language_id,
                'sort_order': item['sort_order'],
                'status': item['status'],
            }

            if title_key in existing_by_title:
                record_id = int(existing_by_title[title_key]['id'])
                saved = importer.update_entity('videos', record_id, payload)
                action = 'updated'
            else:
                saved = importer.create_entity('videos', payload)
                action = 'created'

            results.append(
                {
                    'title': title,
                    'action': action,
                    'record_id': saved['id'],
                    'thumbnail_backend': thumbnail_backend,
                    'video_backend': video_backend,
                    'video_url': final_video_url,
                    'video_error': video_error,
                }
            )
        finally:
            if thumbnail_path and thumbnail_path.exists():
                thumbnail_path.unlink(missing_ok=True)
            if video_path and video_path.exists():
                video_path.unlink(missing_ok=True)

    return results


def print_report(videos: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
    print(f'Crawled {len(videos)} videos from source page.')
    for item in videos:
        print(f"- {item['title']} | duration={item['duration_seconds']}s")

    print('\nImport results:')
    for result in results:
        suffix = f" | fallback_error={result['video_error']}" if result['video_error'] else ''
        print(
            f"- {result['title']} -> {result['action']} #{result['record_id']}"
            f" | thumbnail={result['thumbnail_backend']}"
            f" | video={result['video_backend']}"
            f" | url={result['video_url']}{suffix}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Import video data from en.sinodecor.com into local admin.')
    parser.add_argument('--api-base', default='http://127.0.0.1:8000/api/v1', help='Backend API base URL')
    parser.add_argument('--username', default='admin', help='Admin username')
    parser.add_argument('--password', default='admin123456', help='Admin password')
    parser.add_argument('--language-code', default='en', help='Language code to use for imported videos')
    parser.add_argument(
        '--skip-video-upload',
        action='store_true',
        help='Only upload thumbnails to Cloudinary and keep original video URLs.',
    )
    parser.add_argument(
        '--video-upload-mode',
        choices=['remote-cloudinary', 'admin-upload'],
        default='remote-cloudinary',
        help='Choose how MP4 files are uploaded when video upload is enabled.',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    videos = crawl_source_videos()

    importer = AdminImporter(api_base=args.api_base, username=args.username, password=args.password)
    importer.login()

    language_id = get_language_id(importer, args.language_code)
    results = import_videos(
        importer=importer,
        videos=videos,
        language_id=language_id,
        upload_videos_to_cloudinary=not args.skip_video_upload,
        use_remote_cloudinary_upload=args.video_upload_mode == 'remote-cloudinary',
    )
    print_report(videos, results)


if __name__ == '__main__':
    main()
