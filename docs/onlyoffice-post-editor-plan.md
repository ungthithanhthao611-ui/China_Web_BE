# ONLYOFFICE Integration Plan For News Posts

This plan is aligned with the current codebase:

- Frontend admin: `China_Web_FE/src/admin`
- Backend API: `China_BE/app`
- Current post editor: `China_Web_FE/src/admin/pages/components/posts-manager/PostsManager.vue`

The goal is to add ONLYOFFICE Docs Community Edition as a Word-like editor for post content without breaking the current metadata form and current admin routing.

## PHAN 1: Kien truc + Flow

### 1. Kien truc tong the

Use a 4-part split:

1. Vue 3 admin
   - manages metadata
   - opens a separate route for Word editing
   - fetches ONLYOFFICE config from backend

2. FastAPI backend
   - stores post metadata
   - stores Word document metadata
   - serves document URLs
   - receives ONLYOFFICE callback
   - converts `.docx` to `content_html`

3. ONLYOFFICE Document Server
   - renders the Word editor
   - saves via callback

4. File storage
   - stores `.docx` on disk
   - public frontend renders `content_html`, not `.docx`

### 2. Data ownership

Keep the split strict:

- `posts`
  - title
  - slug
  - category
  - language
  - status
  - featured image
  - excerpt
  - SEO fields
  - `content_html`

- `post_documents`
  - linked `.docx`
  - file path / URL
  - version
  - document key
  - sync timestamps

Do not store `.docx` binary in PostgreSQL.

### 3. Frontend integration strategy

For this project, do not replace the current post form immediately. Add a secondary flow:

1. Admin edits metadata in current `PostsManager.vue`
2. Admin clicks `Open Word Editor`
3. Router opens `/admin/posts/:id/word-editor`
4. That page mounts `OnlyOfficeEditor.vue`
5. After callback save, backend updates `content_html`
6. Existing preview / publish flow keeps using HTML

This keeps the current admin stable while introducing Word editing in isolation.

### 4. Business flow

#### Flow A: Create new post

1. Admin creates post metadata first.
2. Backend creates `posts` row.
3. Admin opens Word editor.
4. Backend ensures one `post_documents` row exists.
5. If no `.docx` exists yet, backend creates a blank `.docx` from a template.
6. Backend returns ONLYOFFICE config.
7. ONLYOFFICE opens the document.

#### Flow B: Save in ONLYOFFICE

1. Admin edits the document.
2. ONLYOFFICE sends callback to backend.
3. Backend validates callback.
4. Backend downloads the latest `.docx`.
5. Backend overwrites stored file.
6. Backend increments version.
7. Backend refreshes `document_key`.
8. Backend converts `.docx` to HTML.
9. Backend updates `posts.content_html`.

#### Flow C: Preview before publish

1. Admin saves the Word file.
2. Backend converts to HTML.
3. Admin previews `content_html`.
4. Admin returns to Word editor if needed.

#### Flow D: Publish

1. Validate metadata.
2. Validate `content_html` exists.
3. Set status to `published`.
4. Public frontend renders `content_html`.

### 5. Why this is production-friendly

- isolates Word editing from metadata
- keeps public rendering independent of ONLYOFFICE uptime
- avoids binary file storage in DB
- allows future replacement of editor vendor
- avoids breaking current `PostsManager.vue`

## PHAN 2: Database + API

### 1. Database model proposal

Recommended `posts` shape:

```python
class Post(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "posts"

    category_id: Mapped[int | None] = mapped_column(ForeignKey("post_categories.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    content_html: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(index=True)
    author: Mapped[str | None] = mapped_column(String(255))
    image_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"))
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True, nullable=False)
    meta_title: Mapped[str | None] = mapped_column(String(255))
    meta_description: Mapped[str | None] = mapped_column(String(500))

    word_document = relationship("PostDocument", back_populates="post", uselist=False)
```

Recommended `post_documents` shape:

```python
class PostDocument(BigIntPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "post_documents"

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(500))
    document_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(index=True)

    post = relationship("Post", back_populates="word_document")
```

### 2. SQL migration example

```sql
ALTER TABLE posts
  ADD COLUMN IF NOT EXISTS excerpt TEXT,
  ADD COLUMN IF NOT EXISTS content_html TEXT;

CREATE TABLE IF NOT EXISTS post_documents (
  id BIGSERIAL PRIMARY KEY,
  post_id BIGINT NOT NULL UNIQUE REFERENCES posts(id) ON DELETE CASCADE,
  file_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(500) NOT NULL,
  file_url VARCHAR(500),
  document_key VARCHAR(255) NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  last_synced_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3. Schema suggestion

```python
class PostDocumentRead(ORMModel):
    id: int
    post_id: int
    file_name: str
    file_path: str
    file_url: str | None
    document_key: str
    version: int
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OnlyOfficeConfigResponse(BaseModel):
    document_server_url: str
    config: dict[str, Any]


class OnlyOfficeCallbackPayload(BaseModel):
    key: str
    status: int
    url: str | None = None
    users: list[str] = []
    actions: list[dict[str, Any]] = []
    userdata: str | None = None
```

### 4. API list

#### `POST /api/v1/admin/posts`

Request:

```json
{
  "title": "Example post",
  "slug": "example-post",
  "category_id": 1,
  "language_id": 1,
  "status": "draft",
  "excerpt": "Short intro",
  "meta_title": "Example post SEO",
  "meta_description": "SEO description"
}
```

#### `POST /api/v1/admin/posts/{id}/document`

Multipart upload for `.docx`.

Response:

```json
{
  "id": 88,
  "post_id": 101,
  "file_name": "example-post.docx",
  "file_url": "http://127.0.0.1:8000/uploads/post-documents/101/example-post.docx",
  "document_key": "post-101-v3-2f8e5e",
  "version": 3
}
```

#### `GET /api/v1/admin/posts/{id}/onlyoffice-config`

Response:

```json
{
  "document_server_url": "http://127.0.0.1:8082",
  "config": {
    "documentType": "word",
    "document": {
      "title": "example-post.docx",
      "url": "http://127.0.0.1:8000/uploads/post-documents/101/example-post.docx",
      "fileType": "docx",
      "key": "post-101-v3-2f8e5e"
    },
    "editorConfig": {
      "mode": "edit",
      "callbackUrl": "http://127.0.0.1:8000/api/v1/admin/onlyoffice/callback",
      "user": {
        "id": "1",
        "name": "admin"
      }
    },
    "token": "jwt-generated-by-backend"
  }
}
```

#### `POST /api/v1/admin/onlyoffice/callback`

Request example:

```json
{
  "key": "post-101-v3-2f8e5e",
  "status": 2,
  "url": "http://onlyoffice/internal/download",
  "users": ["1"]
}
```

Response:

```json
{
  "error": 0
}
```

#### `POST /api/v1/admin/posts/{id}/convert-html`

Response:

```json
{
  "post_id": 101,
  "document_id": 88,
  "content_html": "<p>Hello world</p>",
  "converted_at": "2026-04-16T17:00:00+07:00"
}
```

#### `GET /api/v1/admin/posts/{id}/preview-html`

Returns generated HTML preview.

#### `POST /api/v1/admin/posts/{id}/publish`

Publishes only after `content_html` is ready.

## PHAN 3: Frontend Vue 3

### 1. Frontend folder structure

Recommended:

```text
China_Web_FE/src/admin/
  pages/
    posts/
      PostWordEditorPage.vue
  components/
    onlyoffice/
      OnlyOfficeEditor.vue
  services/
    onlyofficeApi.js
```

### 2. Route example

Current admin router is `China_Web_FE/src/router/admin.routes.js`.

Add:

```js
{
  path: 'posts/:id/word-editor',
  name: 'AdminPostWordEditor',
  component: () => import('@/admin/pages/posts/PostWordEditorPage.vue'),
  meta: { requiresAdminAuth: true },
  props: true,
}
```

### 3. `onlyofficeApi.js`

```js
import { fetchJson } from '@/lib/http'

function withAdminHeaders(token) {
  const normalized = String(token || '').trim()
  if (!normalized) {
    throw new Error('Admin access token is required.')
  }

  return {
    Authorization: `Bearer ${normalized}`,
  }
}

export function getOnlyOfficeConfig(postId, token) {
  return fetchJson(`/admin/posts/${postId}/onlyoffice-config`, {
    headers: withAdminHeaders(token),
    timeoutMs: 30000,
  })
}

export function convertPostDocumentToHtml(postId, token) {
  return fetchJson(`/admin/posts/${postId}/convert-html`, {
    method: 'POST',
    headers: withAdminHeaders(token),
    timeoutMs: 60000,
  })
}
```

### 4. `PostWordEditorPage.vue`

```vue
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ADMIN_TOKEN_STORAGE_KEY } from '@/admin/constants/auth'
import { getAdminEntityRecord } from '@/admin/services/adminApi'
import { convertPostDocumentToHtml, getOnlyOfficeConfig } from '@/admin/services/onlyofficeApi'
import OnlyOfficeEditor from '@/admin/components/onlyoffice/OnlyOfficeEditor.vue'

const route = useRoute()
const router = useRouter()

const token = ref(localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || '')
const post = ref(null)
const editorPayload = ref(null)
const loading = ref(true)
const converting = ref(false)
const errorMessage = ref('')

const postId = computed(() => Number(route.params.id))

async function loadPage() {
  loading.value = true
  errorMessage.value = ''

  try {
    const [postResponse, configResponse] = await Promise.all([
      getAdminEntityRecord('posts', postId.value, token.value),
      getOnlyOfficeConfig(postId.value, token.value),
    ])

    post.value = postResponse
    editorPayload.value = configResponse
  } catch (error) {
    errorMessage.value = error?.message || 'Failed to load ONLYOFFICE editor.'
  } finally {
    loading.value = false
  }
}

async function handleConvertHtml() {
  converting.value = true
  try {
    await convertPostDocumentToHtml(postId.value, token.value)
  } catch (error) {
    errorMessage.value = error?.message || 'Failed to convert DOCX to HTML.'
  } finally {
    converting.value = false
  }
}

function handleBack() {
  router.push({ name: 'AdminDashboard', query: { section: 'posts', postId: postId.value, postView: 'editor' } })
}

onMounted(loadPage)
</script>

<template>
  <section>
    <header>
      <h1>Word Editor</h1>
      <button type="button" @click="handleBack">Back to post</button>
      <button type="button" :disabled="converting" @click="handleConvertHtml">
        {{ converting ? 'Converting...' : 'Convert to HTML' }}
      </button>
    </header>

    <p v-if="errorMessage">{{ errorMessage }}</p>
    <div v-if="loading">Loading editor...</div>

    <OnlyOfficeEditor
      v-else-if="editorPayload?.config"
      :document-server-url="editorPayload.document_server_url"
      :config="editorPayload.config"
    />
  </section>
</template>
```

### 5. `OnlyOfficeEditor.vue`

```vue
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  documentServerUrl: {
    type: String,
    required: true,
  },
  config: {
    type: Object,
    required: true,
  },
})

const containerId = `onlyoffice-editor-${Math.random().toString(36).slice(2)}`
const editorInstance = ref(null)

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`)
    if (existing) {
      resolve()
      return
    }

    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load ONLYOFFICE API script.'))
    document.head.appendChild(script)
  })
}

onMounted(async () => {
  await loadScript(`${props.documentServerUrl}/web-apps/apps/api/documents/api.js`)
  editorInstance.value = new window.DocsAPI.DocEditor(containerId, props.config)
})

onBeforeUnmount(() => {
  if (editorInstance.value?.destroyEditor) {
    editorInstance.value.destroyEditor()
  }
})
</script>

<template>
  <div :id="containerId" style="width: 100%; min-height: calc(100vh - 180px); background: #fff;"></div>
</template>
```

### 6. Entry point from current editor

Inside current post form, add one action:

```js
router.push({
  name: 'AdminPostWordEditor',
  params: { id: editingRecordId.value },
})
```

Only allow this after the post already exists.

## PHAN 4: Backend callback/config

### 1. Backend folder structure

Recommended:

```text
China_BE/app/
  api/routes/
    admin.py
  services/
    onlyoffice.py
    document_conversion.py
    post_documents.py
  schemas/
    onlyoffice.py
  models/
    post_documents.py
```

### 2. `GET /api/v1/admin/posts/{id}/onlyoffice-config`

Route example:

```python
@router.get("/posts/{post_id}/onlyoffice-config")
def get_post_onlyoffice_config(
    post_id: int,
    db: Session = Depends(get_db),
    admin_user: AdminUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return build_onlyoffice_config(db=db, post_id=post_id, admin_user=admin_user)
```

Service example:

```python
from datetime import datetime, timezone
import hashlib

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.config import settings
from app.models.news import Post
from app.models.post_documents import PostDocument


def make_document_key(post_id: int, version: int, updated_at: datetime | None) -> str:
    raw = f"{post_id}:{version}:{(updated_at or datetime.now(timezone.utc)).timestamp()}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"post-{post_id}-v{version}-{digest}"


def build_onlyoffice_config(db, post_id: int, admin_user) -> dict:
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")

    document = db.scalar(select(PostDocument).where(PostDocument.post_id == post_id))
    if not document:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Post has no Word document.")

    callback_url = f"{settings.onlyoffice_callback_base_url.rstrip('/')}{settings.api_v1_prefix}/admin/onlyoffice/callback"

    config = {
        "documentType": "word",
        "document": {
            "title": document.file_name,
            "url": document.file_url,
            "fileType": "docx",
            "key": document.document_key,
        },
        "editorConfig": {
            "mode": "edit",
            "callbackUrl": callback_url,
            "user": {
                "id": str(admin_user.id),
                "name": admin_user.username,
            },
            "customization": {
                "autosave": True,
                "forcesave": True,
            },
        },
    }

    config["token"] = jwt.encode(config, settings.onlyoffice_jwt_secret, algorithm="HS256")
    return {
        "document_server_url": settings.onlyoffice_document_server_url.rstrip("/"),
        "config": config,
    }
```

### 3. `POST /api/v1/admin/onlyoffice/callback`

Practical statuses:

- `2`: ready for saving
- `6`: force-save success

Ignore other statuses with `{ "error": 0 }`.

Route example:

```python
@router.post("/onlyoffice/callback")
async def onlyoffice_callback(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    payload = await request.json()
    await handle_onlyoffice_callback(db=db, payload=payload, headers=request.headers)
    return {"error": 0}
```

Service example:

```python
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select

from app.models.news import Post
from app.models.post_documents import PostDocument


async def handle_onlyoffice_callback(db, payload: dict, headers) -> None:
    callback_status = int(payload.get("status") or 0)
    document_key = str(payload.get("key") or "").strip()

    if not document_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing callback key.")

    document = db.scalar(select(PostDocument).where(PostDocument.document_key == document_key))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if callback_status not in {2, 6}:
        return

    download_url = str(payload.get("url") or "").strip()
    if not download_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing callback download URL.")

    file_path = Path(document.file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
        response = await client.get(download_url)
        response.raise_for_status()
        file_path.write_bytes(response.content)

    document.version += 1
    document.last_synced_at = datetime.now(timezone.utc)
    document.document_key = make_document_key(document.post_id, document.version, document.last_synced_at)

    html = convert_docx_file_to_html(file_path)
    post = db.get(Post, document.post_id)
    post.content_html = html

    db.add(post)
    db.add(document)
    db.commit()
```

### 4. `POST /api/v1/admin/posts/{id}/convert-html`

```python
@router.post("/posts/{post_id}/convert-html")
def convert_post_docx_to_html(
    post_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return convert_post_document_html(db=db, post_id=post_id)
```

```python
from datetime import datetime, timezone
from pathlib import Path

import mammoth
from fastapi import HTTPException, status
from sqlalchemy import select

from app.models.news import Post
from app.models.post_documents import PostDocument


def convert_docx_file_to_html(file_path: Path) -> str:
    with file_path.open("rb") as source:
        result = mammoth.convert_to_html(source)
    return result.value


def convert_post_document_html(db, post_id: int) -> dict:
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")

    document = db.scalar(select(PostDocument).where(PostDocument.post_id == post_id))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word document not found.")

    html = convert_docx_file_to_html(Path(document.file_path))
    post.content_html = html
    document.last_synced_at = datetime.now(timezone.utc)

    db.add(post)
    db.add(document)
    db.commit()

    return {
        "post_id": post.id,
        "document_id": document.id,
        "content_html": html,
        "converted_at": document.last_synced_at,
    }
```

## PHAN 5: Docker + Cau hinh moi truong

### 1. Docker compose sample

Added sample file:

- `China_BE/docker-compose.onlyoffice.yml`

Run:

```powershell
cd E:\uiChina_Web\China_BE
docker compose -f docker-compose.onlyoffice.yml up -d
```

### 2. Backend env variables

Added to `China_BE/.env.example`:

```env
ONLYOFFICE_DOCUMENT_SERVER_URL=http://127.0.0.1:8082
ONLYOFFICE_CALLBACK_BASE_URL=http://127.0.0.1:8000
ONLYOFFICE_JWT_SECRET=change-this-onlyoffice-secret
ONLYOFFICE_STORAGE_DIR=uploads/post-documents
ONLYOFFICE_DOCX_PUBLIC_BASE_URL=http://127.0.0.1:8000/uploads/post-documents
ONLYOFFICE_AUTO_CONVERT_ON_CALLBACK=true
```

### 3. Frontend env variables

Added to `China_Web_FE/.env.example` and exposed through `China_Web_FE/src/config/env.js`:

```env
VITE_ONLYOFFICE_DOCS_URL=http://127.0.0.1:8082
VITE_ONLYOFFICE_CALLBACK_PROXY_URL=http://127.0.0.1:8000
```

### 4. Security and ops notes

1. Enable JWT between backend and ONLYOFFICE.
2. Validate callback document key.
3. Reject callbacks without trusted token or known document key.
4. Store documents under a dedicated folder:
   - `uploads/post-documents/{post_id}/...`
5. Never render raw `.docx` in public frontend.
6. Public pages must render `content_html` only.
7. Keep CORS explicit:
   - admin frontend origin
   - backend origin
   - ONLYOFFICE origin
8. Sanitize converted HTML before public render if needed.
9. Use stable callback base URL reachable from ONLYOFFICE container.

### 5. Local dev notes

Suggested local endpoints:

- frontend: `http://localhost:5173`
- backend: `http://127.0.0.1:8000`
- onlyoffice: `http://127.0.0.1:8082`

If ONLYOFFICE runs in Docker and backend runs on host, ensure the callback URL and file URL are reachable from the container, not only from the browser.

## PHAN 6: Checklist test end-to-end

### 1. Infrastructure

- [ ] ONLYOFFICE container starts
- [ ] browser can load `.../web-apps/apps/api/documents/api.js`
- [ ] backend can write to `uploads/post-documents`
- [ ] ONLYOFFICE can access `.docx` file URL
- [ ] ONLYOFFICE can access backend callback URL

### 2. Metadata flow

- [ ] create post without Word document
- [ ] save title / slug / category / language / status normally
- [ ] keep current admin post form usable without ONLYOFFICE

### 3. Document flow

- [ ] upload `.docx`
- [ ] open Word editor route
- [ ] edit content in ONLYOFFICE
- [ ] save document
- [ ] callback reaches backend
- [ ] stored `.docx` updates on disk
- [ ] `post_documents.version` increments
- [ ] `post_documents.document_key` refreshes

### 4. Conversion flow

- [ ] manual convert endpoint works
- [ ] auto convert on callback works
- [ ] `posts.content_html` updates
- [ ] preview renders generated HTML

### 5. Publish flow

- [ ] publish blocked if HTML not ready
- [ ] publish succeeds after convert
- [ ] public page shows `content_html`
- [ ] public page stays functional even if ONLYOFFICE is down

### 6. Failure cases

- [ ] invalid JWT callback rejected
- [ ] unknown document key rejected
- [ ] missing callback download URL handled safely
- [ ] docx conversion failure handled with clean error
- [ ] deleting a post removes linked `post_documents` row and file

## Recommended implementation order for this project

1. Add `post_documents` model and schema
2. Add file storage service
3. Add ONLYOFFICE config endpoint
4. Add ONLYOFFICE callback endpoint
5. Add manual convert endpoint
6. Add Vue route and dedicated editor page
7. Add button from current post editor to Word editor
8. Add preview + publish validation based on `content_html`

That order is the lowest-risk path for your current admin architecture.
