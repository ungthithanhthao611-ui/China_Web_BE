# Project Case Release Readiness

## Scope

This document covers the release path for the Project Case CMS integration:

- database provenance fields for legacy detail routes
- legacy catalog import
- public contract verification
- admin and frontend smoke verification
- rollback expectations

The public Project Case UI stays unchanged. Legacy public routes must continue to work.

## Data Model

`projects` now stores explicit legacy detail provenance:

- `legacy_detail_id`
- `legacy_detail_href`

These fields replace the temporary use of `meta_title` and `meta_description` for legacy detail tracking.

`initialize_database()` backfills old records when the new columns are missing:

- `meta_title` pattern: `legacy-detail:{id}`
- `meta_description` containing `/project_detail/`

## Import Commands

Import the full legacy catalog:

```powershell
cd e:\uiChina_Web\China_BE
.\.venv\Scripts\python.exe scripts\import_project_case_legacy_catalog.py
```

Import only selected categories:

```powershell
cd e:\uiChina_Web\China_BE
.\.venv\Scripts\python.exe scripts\import_project_case_legacy_catalog.py star-hotel terminal-space
```

Compatibility wrapper:

```powershell
cd e:\uiChina_Web\China_BE
.\.venv\Scripts\python.exe scripts\seed_project_case_catalog.py
```

## Import Behavior

- idempotent reruns update existing categories, projects, mappings, and media links
- importer prints a JSON report with create/update counters
- importer auto-resolves legitimate slug collisions by suffixing with legacy detail id
- importer fails fast on provenance conflicts
- no partial commit is kept when provenance conflicts are detected

Conflict examples:

- slug resolves to one project but legacy detail id/href resolves to another
- an existing project already owns a different non-null legacy detail provenance

## Verification

### Public Contract

`GET /api/v1/public/project-case/{category_id}` and `GET /api/v1/public/project-case?category_id=...`
must expose only:

- `currentCategory`
- `categories`
- `heroSlides`
- `cases`

Each case must expose:

- `anchor`
- `title`
- `summary`
- `detailHref`
- `legacyDetailHref`
- `leftGallery`
- `rightGallery`
- `layoutVariant`

`categories[].projects` is no longer part of the public contract.

### Backend

```powershell
cd e:\uiChina_Web\China_BE
.\.venv\Scripts\python.exe -m pytest -q tests\test_public_project_case_e2e.py tests\test_public_project_case_contract.py tests\test_admin_entity_integrity_conflicts.py tests\test_project_case_importer.py
```

### Frontend Build

```powershell
cd e:\uiChina_Web\China_Web_FE
npm run build
```

### Frontend Smoke

Install Playwright browser once:

```powershell
cd e:\uiChina_Web\China_Web_FE
npx playwright install chromium
```

Run smoke suite:

```powershell
cd e:\uiChina_Web\China_Web_FE
npm run test:smoke
```

### Public Sanity Checks

The following must keep working after import:

- `/api/v1/public/projects`
- `/api/v1/public/projects/{slug}`
- `/api/v1/public/project-case/{category_id}`
- `/project_list/{categoryId}.html`
- `/project_list/{categoryId}.html#ctnX`

## Rollback

Preferred rollback is database-first.

1. Restore the database snapshot taken before import.
2. Restore the backend/frontend release tag that matches that snapshot.
3. Re-run backend and smoke verification.

If only import data is wrong and code is still valid:

1. Fix the source legacy catalog or the conflicting records.
2. Re-run the importer for the affected category slugs.
3. Re-run verification.

Do not use rollback by manually deleting random records from `project_category_items` or `entity_media` unless you have a precise migration plan. The importer is idempotent, but provenance conflicts are intentionally blocking and should be resolved explicitly.

## Release Checklist

1. Run database initialization so provenance fields exist and backfill completes.
2. Run the legacy catalog import.
3. Review the JSON import report.
4. Run backend tests.
5. Run frontend build.
6. Run frontend smoke tests.
7. Verify legacy route and hash navigation manually once on the release environment.
