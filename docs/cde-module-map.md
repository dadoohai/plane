# Plane CDE module map

## Current Plane primitives we can reuse

### File blob + metadata
- Model: `apps/api/plane/db/models/asset.py::FileAsset`
- Current role: generic uploaded file record used by issue attachments, descriptions, comments, pages, avatars, logos, and project covers.
- Key fields already useful for CDE work:
  - `asset` (object key / file path)
  - `attributes` (JSON metadata)
  - `workspace`, `project`, `issue`, `comment`, `page`
  - `entity_type`, `entity_identifier`
  - `size`, `is_uploaded`, `storage_metadata`
  - soft delete flags

### Existing attachment flows
- Issue attachment endpoints already use `FileAsset`
- Relevant paths:
  - `apps/api/plane/api/views/issue.py`
  - `apps/api/plane/app/views/asset/v2.py`
  - `apps/api/plane/api/serializers/issue.py::IssueAttachmentSerializer`

### Existing asset routes
- App-facing asset routes:
  - `apps/api/plane/app/urls/asset.py`
- API-facing asset routes:
  - `apps/api/plane/api/urls/asset.py`

### Storage implementation today
- `apps/api/plane/settings/storage.py::S3Storage`
- Current state:
  - direct presigned POST/GET logic
  - MinIO/S3-oriented
  - no first-class local-filesystem provider abstraction yet

## What is missing for a real CDE

`FileAsset` is useful as the low-level binary/blob record, but it is not yet a real CDE document model.

### Missing domain concepts
1. `Document`
   - logical document within a project
   - title, discipline, code, status, folder, source, sharing posture
2. `DocumentVersion`
   - versioned wrapper over one `FileAsset`
   - revision label, current flag, version number, checksum, published state
3. `DocumentFolder`
   - project folder tree / drive-style explorer
4. `DocumentShare`
   - internal/external sharing with expiry and permissions
5. `DocumentReview`
   - review workflow, approval state, transmittal-like flows
6. `DocumentAnnotation`
   - comments pinned to PDF page coordinates or IFC element references
7. `DocumentLink`
   - explicit relation between documents and Plane entities (issue, page, comment, cycle, module)
8. `DocumentEmbedding` / extraction jobs
   - semantic search and agentic layer

## Architectural decision

### Reuse
- Reuse `FileAsset` as the **physical binary object record**.
- Reuse existing issue attachment activity patterns as a starting point for review/activity logging.

### Add
Create a dedicated CDE domain on top of Plane instead of stretching `FileAsset` into the whole product domain.

Recommended new app: `plane.cde` (or `plane.document_control` if we want a more explicit name).

## First implementation slices

### Slice 1 — storage abstraction
Introduce a storage provider layer so CDE can run with:
- S3 / MinIO
- local filesystem

This should sit above the current `S3Storage` implementation and become the new access point for upload/download/presign/copy/delete.

### Slice 2 — document domain
Add models for:
- `DocumentFolder`
- `Document`
- `DocumentVersion`
- `DocumentLink`

`DocumentVersion.file_asset -> FileAsset`

### Slice 3 — project-facing APIs
Start with project-scoped endpoints:
- list folders/documents
- create folder
- request upload
- confirm upload
- list versions
- download version
- link document to issue

### Slice 4 — CDE workflow
Add:
- review state
- published/shared/archive states
- review requests
- audit trail

### Slice 5 — agentic layer
Add extraction/index entities for:
- OCR text
- PDF chunks
- IFC properties/elements
- embeddings
- agent tasks / summaries / change detection

## Why not model the CDE directly as issue attachments
Because that would make the product behave like “issues with files” instead of “project documents with workflow”.

The CDE needs:
- first-class folder navigation
- first-class version history
- first-class sharing
- first-class review/publish lifecycle
- cross-linking to issues (not subordination to issues)

## Recommended code entry points for next step
1. `apps/api/plane/settings/storage.py`
   - extract provider abstraction
2. `apps/api/plane/db/models/asset.py`
   - keep `FileAsset` as blob record
3. new app for CDE domain models and API
4. project-facing routes under app/api namespaces for project documents

## Immediate next coding target
Implement storage abstraction first, because it unlocks the local-filesystem fallback required for the CDE.
