from sqlalchemy import select

from app.models.media import EntityMedia, MediaAsset
from app.models.projects import Project, ProjectCategory, ProjectCategoryItem
from scripts.import_project_case_legacy_catalog import ImportReport, resolve_project, seed_category


def _category_seed() -> dict:
    return {
        "id": 1676767239059300352,
        "name": "Star Hotel",
        "slug": "star-hotel",
        "description": "Star Hotel project case category.",
        "sort_order": 10,
        "hero": {
            "desktop": "https://example.com/hero-desktop.jpg",
            "mobile": "https://example.com/hero-mobile.jpg",
        },
        "projects": [
            {
                "title": "W HOTEL",
                "slug": "w-hotel",
                "summary": "W hotel summary",
                "anchor": "ctn2",
                "layout_variant": "feature",
                "is_featured": True,
                "legacy_detail_id": "1676516550370418688",
                "legacy_detail_href": "/project_detail/1676516550370418688.html",
                "left_gallery": ["https://example.com/left-1.jpg"],
                "right_gallery": ["https://example.com/right-1.jpg"],
            }
        ],
    }


def test_seed_category_is_idempotent_and_reports_updates(db_session) -> None:
    seed = _category_seed()

    first_report = ImportReport(selected_categories=[seed["slug"]])
    seed_category(
        db_session,
        first_report,
        language_id=1,
        category_seed=seed,
        used_slugs=set(),
    )
    db_session.commit()

    assert first_report.categories_created == 1
    assert first_report.projects_created == 1
    assert first_report.mappings_created == 1
    assert first_report.media_created == 4
    assert first_report.entity_media_created == 4

    second_report = ImportReport(selected_categories=[seed["slug"]])
    used_slugs = {slug for slug in db_session.scalars(select(Project.slug)).all() if slug}
    seed_category(
        db_session,
        second_report,
        language_id=1,
        category_seed=seed,
        used_slugs=used_slugs,
    )
    db_session.commit()

    assert second_report.categories_updated == 1
    assert second_report.projects_updated == 1
    assert second_report.mappings_updated == 1
    assert second_report.media_updated == 4
    assert second_report.entity_media_updated == 4

    assert db_session.scalar(select(ProjectCategory).where(ProjectCategory.slug == "star-hotel")) is not None
    assert db_session.scalar(select(Project).where(Project.slug == "w-hotel")) is not None
    assert db_session.query(ProjectCategoryItem).count() == 1
    assert db_session.query(MediaAsset).count() == 4
    assert db_session.query(EntityMedia).count() == 4


def test_resolve_project_collects_conflict_for_mismatched_provenance(db_session) -> None:
    existing_slug_match = Project(
        title="W HOTEL",
        slug="w-hotel",
        summary="old summary",
        body="old summary",
        language_id=1,
        status="published",
        legacy_detail_id="111",
        legacy_detail_href="/project_detail/111.html",
    )
    existing_provenance_match = Project(
        title="W HOTEL ALT",
        slug="w-hotel-alt",
        summary="legacy summary",
        body="legacy summary",
        language_id=1,
        status="published",
        legacy_detail_id="222",
        legacy_detail_href="/project_detail/222.html",
    )
    db_session.add_all([existing_slug_match, existing_provenance_match])
    db_session.commit()

    report = ImportReport()
    resolved = resolve_project(
        db_session,
        report,
        language_id=1,
        category_id=1676767239059300352,
        item={
            "title": "W HOTEL",
            "slug": "w-hotel",
            "summary": "new summary",
            "legacy_detail_id": "222",
            "legacy_detail_href": "/project_detail/222.html",
        },
        used_slugs={"w-hotel"},
    )

    assert resolved.id == existing_provenance_match.id
    assert report.conflicts
    assert "legacy provenance resolves" in report.conflicts[0]


def test_resolve_project_creates_unique_slug_for_slug_collision_without_provenance_match(db_session) -> None:
    existing = Project(
        title="BEIJING HOTEL",
        slug="beijing-hotel",
        summary="old summary",
        body="old summary",
        language_id=1,
        status="published",
        legacy_detail_id="111",
        legacy_detail_href="/project_detail/111.html",
    )
    db_session.add(existing)
    db_session.commit()

    report = ImportReport()
    resolved = resolve_project(
        db_session,
        report,
        language_id=1,
        category_id=1676767239059300352,
        item={
            "title": "BEIJING HOTEL",
            "slug": "beijing-hotel",
            "summary": "new summary",
            "legacy_detail_id": "222",
            "legacy_detail_href": "/project_detail/222.html",
        },
        used_slugs={"beijing-hotel"},
    )
    db_session.commit()

    assert resolved.id != existing.id
    assert resolved.slug == "beijing-hotel-222"
    assert report.slug_collisions_resolved == 1
    assert not report.conflicts
