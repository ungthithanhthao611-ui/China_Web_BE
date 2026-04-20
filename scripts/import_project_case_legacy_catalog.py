from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.init_db import initialize_database
from app.db.session import SessionLocal
from app.models.media import EntityMedia, MediaAsset
from app.models.projects import Project, ProjectCategory, ProjectCategoryItem
from app.models.taxonomy import Language

ENTITY_TYPE_PROJECT_CATEGORY = "project_category"
ENTITY_TYPE_PROJECT = "project"
DEFAULT_LANGUAGE_CODE = "en"
DEFAULT_BASE_URL = "https://en.sinodecor.com"
LEGACY_DATA_PATH = PROJECT_ROOT.parent / "China_Web_FE" / "src" / "client" / "pages" / "projects" / "projectCaseData.js"


@dataclass
class ImportReport:
    selected_categories: list[str] = field(default_factory=list)
    categories_created: int = 0
    categories_updated: int = 0
    projects_created: int = 0
    projects_updated: int = 0
    mappings_created: int = 0
    mappings_updated: int = 0
    media_created: int = 0
    media_updated: int = 0
    entity_media_created: int = 0
    entity_media_updated: int = 0
    slug_collisions_resolved: int = 0
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "selected_categories": self.selected_categories,
            "categories_created": self.categories_created,
            "categories_updated": self.categories_updated,
            "projects_created": self.projects_created,
            "projects_updated": self.projects_updated,
            "mappings_created": self.mappings_created,
            "mappings_updated": self.mappings_updated,
            "media_created": self.media_created,
            "media_updated": self.media_updated,
            "entity_media_created": self.entity_media_created,
            "entity_media_updated": self.entity_media_updated,
            "slug_collisions_resolved": self.slug_collisions_resolved,
            "conflicts": self.conflicts,
        }


def slugify(value: str) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("&", " and ")
        .replace("'", "")
        .replace("Â·", "-")
        .replace(".", "-")
        .replace("/", "-")
    )


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", slugify(value))
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "project-case"


def normalize_url(base_url: str, url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/"):
        return f"{base_url.rstrip('/')}{text}"
    return text


def media_file_name(slug: str, suffix: str, url: str) -> str:
    extension = Path(urlparse(url).path).suffix or ".jpg"
    return f"{slug}-{suffix}{extension}"


def extract_legacy_detail_id(url: str) -> str:
    match = re.search(r"/project_detail/(\d+)\.html", str(url or ""))
    return match.group(1) if match else ""


def load_legacy_catalog() -> dict:
    if not LEGACY_DATA_PATH.exists():
        raise RuntimeError(f"Legacy catalog source not found: {LEGACY_DATA_PATH}")

    js_path = LEGACY_DATA_PATH.resolve().as_uri()
    script = "\n".join(
        [
            f"import {{ projectCaseData }} from '{js_path}';",
            "console.log(JSON.stringify(projectCaseData));",
        ]
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-"],
        input=script,
        capture_output=True,
        text=True,
        check=True,
        cwd=str(LEGACY_DATA_PATH.parent.parent.parent.parent.parent.parent),
    )
    return json.loads(completed.stdout)


def build_seed_rows(catalog: dict, category_slugs: set[str] | None = None) -> list[dict]:
    base_url = str(catalog.get("baseUrl") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    selected_slugs = {str(slug).strip() for slug in (category_slugs or set()) if str(slug).strip()}

    hero_by_title = {
        str(slide.get("title") or "").strip().lower(): {
            "desktop": normalize_url(base_url, (slide.get("images") or [""])[0] if slide.get("images") else ""),
            "mobile": normalize_url(
                base_url,
                (slide.get("images") or ["", ""])[1] if len(slide.get("images") or []) > 1 else ((slide.get("images") or [""])[0] if slide.get("images") else ""),
            ),
        }
        for slide in catalog.get("heroSlides", [])
    }

    seed_rows: list[dict] = []
    for index, category in enumerate(catalog.get("categories", []), start=1):
        category_name = str(category.get("name") or "").strip()
        if not category_name:
            continue

        category_slug = normalize_slug(category_name)
        if selected_slugs and category_slug not in selected_slugs:
            continue

        hero = hero_by_title.get(category_name.lower(), {})
        projects = []
        for project_index, item in enumerate(category.get("projects", []), start=1):
            title = str(item.get("title") or "").strip()
            if not title:
                continue

            legacy_detail_href = normalize_url(base_url, item.get("moreLink") or "")
            legacy_detail_id = extract_legacy_detail_id(legacy_detail_href)
            projects.append(
                {
                    "title": title,
                    "slug": normalize_slug(title),
                    "summary": str(item.get("summary") or "").strip(),
                    "anchor": str(item.get("id") or f"ctn{project_index + 1}").strip(),
                    "layout_variant": "feature" if project_index % 2 == 1 else "standard",
                    "is_featured": project_index % 2 == 1,
                    "legacy_detail_href": legacy_detail_href or None,
                    "legacy_detail_id": legacy_detail_id or None,
                    "left_gallery": [normalize_url(base_url, url) for url in item.get("leftImages", []) if str(url or "").strip()],
                    "right_gallery": [normalize_url(base_url, url) for url in item.get("rightImages", []) if str(url or "").strip()],
                }
            )

        seed_rows.append(
            {
                "id": int(str(category.get("id")).strip()),
                "name": category_name,
                "slug": category_slug,
                "description": f"{category_name} project case category.",
                "sort_order": index * 10,
                "hero": {
                    "desktop": hero.get("desktop", ""),
                    "mobile": hero.get("mobile", "") or hero.get("desktop", ""),
                },
                "projects": projects,
            }
        )

    return seed_rows


def upsert_media(
    session,
    report: ImportReport,
    *,
    uuid: str,
    url: str,
    title: str,
    file_name: str,
) -> MediaAsset:
    record = session.scalar(select(MediaAsset).where(MediaAsset.uuid == uuid))
    if record:
        record.url = url
        record.title = title
        record.file_name = file_name
        record.asset_type = "image"
        record.mime_type = "image/jpeg"
        record.status = "active"
        session.add(record)
        session.flush()
        report.media_updated += 1
        return record

    record = MediaAsset(
        uuid=uuid,
        url=url,
        title=title,
        file_name=file_name,
        asset_type="image",
        mime_type="image/jpeg",
        status="active",
    )
    session.add(record)
    session.flush()
    report.media_created += 1
    return record


def upsert_entity_media(
    session,
    report: ImportReport,
    *,
    entity_type: str,
    entity_id: int,
    group_name: str,
    media_id: int,
    sort_order: int,
    caption: str | None = None,
) -> EntityMedia:
    record = session.scalar(
        select(EntityMedia).where(
            EntityMedia.entity_type == entity_type,
            EntityMedia.entity_id == entity_id,
            EntityMedia.group_name == group_name,
            EntityMedia.media_id == media_id,
        )
    )
    if record:
        record.sort_order = sort_order
        record.caption = caption
        session.add(record)
        report.entity_media_updated += 1
        return record

    record = EntityMedia(
        entity_type=entity_type,
        entity_id=entity_id,
        group_name=group_name,
        media_id=media_id,
        sort_order=sort_order,
        caption=caption,
    )
    session.add(record)
    report.entity_media_created += 1
    return record


def resolve_project(
    session,
    report: ImportReport,
    *,
    language_id: int,
    category_id: int,
    item: dict,
    used_slugs: set[str],
) -> Project:
    legacy_detail_id = str(item.get("legacy_detail_id") or "").strip() or None
    legacy_detail_href = str(item.get("legacy_detail_href") or "").strip() or None
    title = item["title"]

    provenance_match = None
    if legacy_detail_href:
        provenance_match = session.scalar(
            select(Project).where(
                Project.language_id == language_id,
                Project.legacy_detail_href == legacy_detail_href,
            )
        )
    if provenance_match is None and legacy_detail_id:
        provenance_match = session.scalar(
            select(Project).where(
                Project.language_id == language_id,
                Project.legacy_detail_id == legacy_detail_id,
            )
        )

    slug_match = session.scalar(
        select(Project).where(
            Project.language_id == language_id,
            Project.slug == item["slug"],
        )
    )
    if provenance_match and slug_match and slug_match.id != provenance_match.id:
        report.conflicts.append(
            f"Slug '{item['slug']}' points to project #{slug_match.id} but legacy provenance resolves to project #{provenance_match.id}."
        )
        return provenance_match

    record = provenance_match or slug_match
    should_generate_unique_slug = False

    if record and slug_match and record.id == slug_match.id:
        existing_detail_id = str(slug_match.legacy_detail_id or "").strip() or None
        existing_detail_href = str(slug_match.legacy_detail_href or "").strip() or None
        incoming_mismatch = (
            (legacy_detail_id and existing_detail_id and legacy_detail_id != existing_detail_id)
            or (legacy_detail_href and existing_detail_href and legacy_detail_href != existing_detail_href)
        )
        if incoming_mismatch:
            if provenance_match is None:
                record = None
                should_generate_unique_slug = True
            else:
                report.conflicts.append(
                    f"Project slug '{slug_match.slug}' has conflicting legacy provenance "
                    f"(existing id={existing_detail_id or '-'}, href={existing_detail_href or '-'}) "
                    f"vs incoming id={legacy_detail_id or '-'}, href={legacy_detail_href or '-'}."
                )
                return slug_match

    if record is None:
        slug = item["slug"]
        if slug in used_slugs:
            if should_generate_unique_slug:
                report.slug_collisions_resolved += 1
            collision_suffix = legacy_detail_id[-8:] if legacy_detail_id else normalize_slug(title)[:12]
            slug = f"{slug}-{collision_suffix}"
            counter = 2
            while slug in used_slugs:
                slug = f"{item['slug']}-{collision_suffix}-{counter}"
                counter += 1
        record = Project(
            category_id=category_id,
            title=title,
            slug=slug,
            summary=item["summary"],
            body=item["summary"],
            location=None,
            project_year=None,
            language_id=language_id,
            status="published",
            legacy_detail_id=legacy_detail_id,
            legacy_detail_href=legacy_detail_href,
        )
        session.add(record)
        session.flush()
        used_slugs.add(record.slug)
        report.projects_created += 1
        return record

    record.category_id = record.category_id or category_id
    record.title = title
    record.summary = item["summary"]
    record.body = item["summary"]
    record.status = "published"
    if legacy_detail_id:
        record.legacy_detail_id = legacy_detail_id
    if legacy_detail_href:
        record.legacy_detail_href = legacy_detail_href
    session.add(record)
    session.flush()
    used_slugs.add(record.slug)
    report.projects_updated += 1
    return record


def upsert_project_category_item(
    session,
    report: ImportReport,
    *,
    category_id: int,
    project_id: int,
    sort_order: int,
    anchor: str,
    layout_variant: str,
    is_featured: bool,
) -> ProjectCategoryItem:
    record = session.scalar(
        select(ProjectCategoryItem).where(
            ProjectCategoryItem.category_id == category_id,
            ProjectCategoryItem.anchor == anchor,
        )
    )
    if record is None:
        record = session.scalar(
            select(ProjectCategoryItem).where(
                ProjectCategoryItem.category_id == category_id,
                ProjectCategoryItem.project_id == project_id,
            )
        )

    if record:
        record.project_id = project_id
        record.sort_order = sort_order
        record.anchor = anchor
        record.layout_variant = layout_variant
        record.is_featured = is_featured
        session.add(record)
        report.mappings_updated += 1
        return record

    record = ProjectCategoryItem(
        category_id=category_id,
        project_id=project_id,
        sort_order=sort_order,
        anchor=anchor,
        layout_variant=layout_variant,
        is_featured=is_featured,
    )
    session.add(record)
    report.mappings_created += 1
    return record


def seed_category(
    session,
    report: ImportReport,
    *,
    language_id: int,
    category_seed: dict,
    used_slugs: set[str],
) -> None:
    category = session.get(ProjectCategory, category_seed["id"])
    if category is None:
        category = session.scalar(select(ProjectCategory).where(ProjectCategory.slug == category_seed["slug"]))

    if category is None:
        category = ProjectCategory(
            id=category_seed["id"],
            name=category_seed["name"],
            slug=category_seed["slug"],
            description=category_seed["description"],
            status="active",
            sort_order=category_seed["sort_order"],
        )
        session.add(category)
        session.flush()
        report.categories_created += 1
    else:
        category.name = category_seed["name"]
        category.slug = category_seed["slug"]
        category.description = category_seed["description"]
        category.status = "active"
        category.sort_order = category_seed["sort_order"]
        session.add(category)
        session.flush()
        report.categories_updated += 1

    if category_seed["hero"]["desktop"]:
        hero_desktop = upsert_media(
            session,
            report,
            uuid=f"project-case-{category_seed['slug']}-hero-desktop",
            title=f"{category_seed['name']} hero desktop",
            file_name=media_file_name(category_seed["slug"], "hero-desktop", category_seed["hero"]["desktop"]),
            url=category_seed["hero"]["desktop"],
        )
        upsert_entity_media(
            session,
            report,
            entity_type=ENTITY_TYPE_PROJECT_CATEGORY,
            entity_id=category.id,
            group_name="hero_desktop",
            media_id=hero_desktop.id,
            sort_order=1,
        )

    if category_seed["hero"]["mobile"]:
        hero_mobile = upsert_media(
            session,
            report,
            uuid=f"project-case-{category_seed['slug']}-hero-mobile",
            title=f"{category_seed['name']} hero mobile",
            file_name=media_file_name(category_seed["slug"], "hero-mobile", category_seed["hero"]["mobile"]),
            url=category_seed["hero"]["mobile"],
        )
        upsert_entity_media(
            session,
            report,
            entity_type=ENTITY_TYPE_PROJECT_CATEGORY,
            entity_id=category.id,
            group_name="hero_mobile",
            media_id=hero_mobile.id,
            sort_order=1,
        )

    for index, item in enumerate(category_seed["projects"], start=1):
        project = resolve_project(
            session,
            report=report,
            language_id=language_id,
            category_id=category.id,
            item=item,
            used_slugs=used_slugs,
        )

        upsert_project_category_item(
            session,
            report,
            category_id=category.id,
            project_id=project.id,
            sort_order=index,
            anchor=item["anchor"],
            layout_variant=item["layout_variant"],
            is_featured=item["is_featured"],
        )

        for media_index, url in enumerate(item["left_gallery"], start=1):
            media = upsert_media(
                session,
                report,
                uuid=f"project-case-{project.slug}-left-{media_index}",
                title=f"{item['title']} left gallery {media_index}",
                file_name=media_file_name(project.slug, f"left-{media_index}", url),
                url=url,
            )
            upsert_entity_media(
                session,
                report,
                entity_type=ENTITY_TYPE_PROJECT,
                entity_id=project.id,
                group_name="left_gallery",
                media_id=media.id,
                sort_order=media_index,
            )

        for media_index, url in enumerate(item["right_gallery"], start=1):
            media = upsert_media(
                session,
                report,
                uuid=f"project-case-{project.slug}-right-{media_index}",
                title=f"{item['title']} right gallery {media_index}",
                file_name=media_file_name(project.slug, f"right-{media_index}", url),
                url=url,
            )
            upsert_entity_media(
                session,
                report,
                entity_type=ENTITY_TYPE_PROJECT,
                entity_id=project.id,
                group_name="right_gallery",
                media_id=media.id,
                sort_order=media_index,
            )


def run(category_slugs: set[str] | None = None) -> None:
    initialize_database()
    catalog = load_legacy_catalog()
    seed_rows = build_seed_rows(catalog, category_slugs=category_slugs)

    with SessionLocal() as session:
        language = session.scalar(select(Language).where(Language.code == DEFAULT_LANGUAGE_CODE))
        if not language:
            raise RuntimeError("Language 'en' is required before importing project case data.")

        used_slugs = {
            str(slug).strip()
            for slug in session.scalars(select(Project.slug).where(Project.language_id == language.id)).all()
            if str(slug).strip()
        }

        report = ImportReport(selected_categories=[row["slug"] for row in seed_rows])
        for category_seed in seed_rows:
            seed_category(
                session,
                report,
                language_id=language.id,
                category_seed=category_seed,
                used_slugs=used_slugs,
            )
        if report.conflicts:
            session.rollback()
            conflict_summary = "; ".join(report.conflicts[:5])
            if len(report.conflicts) > 5:
                conflict_summary = f"{conflict_summary}; and {len(report.conflicts) - 5} more"
            raise RuntimeError(f"Project Case import aborted due to provenance conflicts: {conflict_summary}")

        session.commit()
        print(json.dumps(report.to_dict(), indent=2))


if __name__ == "__main__":
    selected_slugs = {str(argument).strip() for argument in sys.argv[1:] if str(argument).strip()}
    run(selected_slugs or None)

