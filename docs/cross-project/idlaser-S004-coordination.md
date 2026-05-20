# Cross-repo coordination — OrderHub → idlaser (S004-mcp-wrapper)

**From:** OrderHub-side Cowork (OrderHub CRM repo)
**To:** idlaser-side Cowork (idlaser pipeline repo)
**Date:** 2026-05-18
**Sprint:** S004-mcp-wrapper — CRM integration of card-detection pipeline
**Master contract:** `idlaser/task.md` (15 Behaviour rules, 10 OQs). I have read it in full. **No hard contradictions with CRM reality** — all 15 rules implementable as written.

This document delivers items A–F requested in your S004 brief. Forward as-is to your CC session B / planning agent. All file:line refs are CRM-side (OrderHub repo).

---

## A. OrderHub `CLAUDE.md` (current contents — but see F.1, partly stale)

⚠️ **Do NOT trust CLAUDE.md as ground truth for versions or router list.** Use live code + `docs/AI_ONBOARDING.md` + `implementation_plan.md` as authoritative. Corrections in §F.1 below.

```markdown
# CLAUDE.md — OrderHub CRM

> **New AI / agent sessions:** read `docs/AI_ONBOARDING.md` first — it covers the three-actor workflow (Sergii / Cowork / CC), tooling + path mapping (UNC vs sandbox), `task.md` writing pattern, and recurring gotchas. Then this file for project rules and conventions, then `implementation_plan.md` for current state and backlog.

## Project Overview

OrderHub is a multi-channel order management CRM for a Ukrainian handcrafted leather goods business. It aggregates orders from Etsy (CSV), Shopify (API sync), and manual entry into a unified pipeline with logistics automation via Nova Poshta.

**Stack**: Python 3.11 + FastAPI (backend), React 18 + TypeScript + Vite (frontend), PostgreSQL + SQLAlchemy + Alembic (DB), JWT auth with token rotation.
[STALE — actual: Python 3.12 in Dockerfile, React 19.2.4 in package.json]

## Architecture (Key Decisions)

- **Monorepo**: `/backend` and `/frontend` at root level, `/docs` for documentation.
- **Routers**: `backend/routers/` — one file per domain (orders, shops, dashboard, imports, users, auth, shipping, mcp).
  [STALE — actually also: finance, partner_payouts, attachments, products, packaging, materials, overhead_materials, customers]
- **Services**: `backend/services/` — business logic separated from routes.
- **Frontend pages**: `frontend/src/pages/` — one page component per route.
- **Component hierarchy**: `components/layout/` (shell, topbar), `components/ui/` (reusable), `components/orders/` (order-specific with `detail/` sub-components).
- **State**: Zustand for auth (`authStore.ts`). React Query for server state. No Redux.
- **API client**: `frontend/src/api/` — Axios with interceptors for JWT refresh and error handling.
- **Styling**: Tailwind CSS with zinc-950 dark theme. No CSS modules.

## Code Style & Conventions

- Backend: snake_case, type hints on all function signatures, Pydantic models for request/response.
- Frontend: PascalCase components, camelCase functions/variables, TypeScript strict mode.
- Imports: group by stdlib → third-party → local, alphabetical within groups.
- Error handling: backend returns structured `{"detail": "..."}` errors. Frontend shows via Toast component.
- No `any` type in TypeScript unless migrating legacy code (mark with `// TODO: type properly`).

## Behavioral Guidelines

1. Think before coding (state assumptions, present tradeoffs).
2. Simplicity first (no speculative features, no abstractions for single-use code).
3. Surgical changes (touch only what task requires).
4. Verify your work (tests, typecheck, lint at every step).
5. Respect what exists (read existing code before proposing changes).

## Gotchas

- Order status changes MUST go through the audit logging path — never update status directly in DB.
- Frontend `OrderDetailPanel` was refactored into 8 sub-components in `detail/` — don't re-merge them.
- Backend logs rotate at 25MB cap in `backend/logs/server.log`.
- `CreateOrderPage.tsx` is a full-page form, not a modal — deliberate UX decision.
- MCP server development is paused — do not modify `backend/routers/mcp.py` unless explicitly asked.
- Designer shop access (SEC-05): designer access requires ≥1 assigned order in shop. Zero assignments → 403 on shop-scoped endpoints.
- Designer access is shop-scoped, not order-scoped: fine-grained order-level checks only in orders and attachments routers.
- System user UUID `00000000-0000-0000-0000-000000000001` (`backend/constants.py:SYSTEM_USER_ID`) — webhook/scheduler audit rows; never delete/reuse.

## Database Conventions

- All models use SQLAlchemy ORM with Alembic migrations. Never modify DB schema directly — always create a migration.
- Enums in Python must match DB enum types exactly. Adding a new enum value → Alembic `ALTER TYPE` migration.
- Order status mutations are logged in `order_audit_history` table.
  [STALE — actual table name is `order_status_history`, model `OrderStatusHistory` at backend/models/order.py:255]
```

Full file is 116 lines. Above shows the substantive content with [STALE] annotations on the lines that don't match reality.

---

## B. Git log (last 15 commits) + working tree state

```
73975b9 (HEAD -> main, origin/main) docs(part-1-fu-1): close sprint with in-app confirm dialog for partner payout deletes
93f45ca feat(part-1-fu-1): in-app confirm dialog for partner payout deletes
1195bcb docs(part-1): close sprint with partner payouts + payments ledger + shipping net kpi
bd6e528 feat(part-1): partner payouts + payments ledger + shipping net kpi
2b5c288 docs(part-1): sprint spec for partner payouts monoblock
c350be3 chore: add dev startup script
697faa0 docs(part-1): finalize partner-payouts + profit-definition v1.1
8d3c381 docs: close NP-ROBUSTNESS-1 sprint
0e0f82a docs(partner-payouts): add Phase 2 design + profit-definition reference
9a6899a fix(np): idempotent TTN delete + sender phone validation/normalization
3d7ea66 docs(micro-cleanups-1): close sprint, retire 3 followups
a48c73e fix(polish): MAT-4 currency warning grammar + order link in ledger, NP dict-shape errors
50903af docs(mat-5): close sprint, close Phase 3 (Materials Warehouse) epic
60ecad2 feat(materials): MAT-5 P&L integration + Phase B COGS cutover
71d88f6 docs(mat-4): close sprint with smoke evidence

Working tree:
  M task.md           ← Intentionally uncommitted per AI_ONBOARDING §9.
                        Currently contains PART-1-fu-1 spec; will be rewritten for S004.

Branch:  main
Origin:  pushed (HEAD == origin/main)
```

Commit conventions: `feat(<area>):`, `fix(<area>):`, `docs(<sprint-id>):`, `chore:`, `refactor(<area>):`. Cowork docs commits land separately from CC code commits.

---

## C. Sample Order JSON (real response, lightly anonymized)

`GET /api/orders/fcafdf00-2db5-4399-94dd-5db8b80761fb` (Heavy Mushroom Keychain, IN_PRODUCTION):

```json
{
    "external_id": "7148183421084",
    "status": "in_production",
    "title": "Heavy Mushroom Keychain",
    "total_price": 22.99,
    "currency": "USD",
    "production_cost": null,
    "shipping_np_cost": null,
    "platform_fee": null,
    "shipping_name": "Unknown Shopify Customer",
    "shipping_phone": null,
    "shipping_street_1": null,
    "shipping_street_2": null,
    "shipping_city": "Lisbon Falls",
    "shipping_state": "ME",
    "shipping_zip": null,
    "shipping_country": "US",
    "shipping_city_ref": null,
    "shipping_warehouse_ref": null,
    "customer_note": null,
    "custom_info": null,
    "internal_note": null,
    "ordered_at": "2026-05-07T16:49:21Z",
    "shipped_at": "2026-05-14T08:32:27.222776Z",
    "completed_at": null,
    "ttn_number": null,
    "ttn_created_at": null,
    "ttn_printed": false,
    "id": "fcafdf00-2db5-4399-94dd-5db8b80761fb",
    "shop_id": "1b82b96e-bfd9-4b5d-bff2-7b927e379064",
    "customer_id": "27ae6691-c596-443f-9ce0-7c8f6e7cc5d8",
    "assigned_designer_id": null,
    "assigned_at": null,
    "created_at": "2026-05-09T13:16:50.945476Z",
    "updated_at": "2026-05-14T19:42:15.382560Z",
    "shop_name": "Lamamarka Shopify",
    "customer_name": "Unknown Shopify Customer",
    "platform": "shopify",
    "packaging_id": null,
    "items": [
        {
            "id": "d70c6e99-4442-4243-bd72-d7fe078c1fa8",
            "listing_id": null,
            "sku": null,
            "title": "Heavy Mushroom Keychain",
            "quantity": 1,
            "unit_price": 14.99,
            "currency": "USD",
            "variations": null,
            "product_variant_id": "d45d2fa9-423f-4d46-8b67-9dfc3c7fd65f",
            "snapshot_weight_g": 100,
            "snapshot_length_mm": 0,
            "snapshot_width_mm": 0,
            "snapshot_height_mm": 0,
            "snapshot_title": "Heavy Mushroom Keychain",
            "created_at": "2026-04-25T17:11:54.840662Z"
        }
    ],
    "status_history": [
        {
            "id": "9073765f-af3f-4d53-b1b0-0afcf37326a1",
            "from_status": "new",
            "to_status": "shipped",
            "comment": null,
            "changed_at": "2026-04-25T17:11:54.840662Z",
            "changed_by_name": "Микола Шевченко"
        },
        {
            "id": "06b129c9-4aa9-4c7f-b4af-fc7aad822744",
            "from_status": "shipped",
            "to_status": "in_production",
            "comment": null,
            "changed_at": "2026-04-25T17:11:54.840662Z",
            "changed_by_name": "Микола Шевченко"
        },
        {
            "id": "4dae3aa5-bd00-4f4c-9f0c-5f61f909fa84",
            "from_status": "in_production",
            "to_status": "shipped",
            "comment": null,
            "changed_at": "2026-04-25T17:11:54.840662Z",
            "changed_by_name": "Микола Шевченко"
        },
        {
            "id": "7d8cb3d3-b0fe-4a92-8ec2-7d0caed35153",
            "from_status": "shipped",
            "to_status": "in_production",
            "comment": null,
            "changed_at": "2026-04-25T17:11:54.840662Z",
            "changed_by_name": "Микола Шевченко"
        },
        {
            "id": "daa99bbc-b195-4b7f-9c8e-e957aa176441",
            "from_status": "none",
            "to_status": "new",
            "comment": "Order manually created",
            "changed_at": "2026-04-25T17:11:54.840662Z",
            "changed_by_name": "Микола Шевченко"
        }
    ],
    "packaging": null,
    "computed_production_cost": null,
    "warnings": []
}
```

**Observations for idlaser planner:**

- `assigned_designer_id` is **null** for this order → per [master rule 10], DESIGNER role would 403 here; only OWNER and MANAGER can trigger Generate Draft. This is the common case in current production data.
- `computed_production_cost` is null even though MAT-4 hook is supposed to populate it on SHIPPED. The order has gone through SHIPPED twice per `status_history` — yet null. Either the hook didn't fire historically (it's recent), or it resets on IN_PRODUCTION transitions. Not blocking idlaser, just FYI when reading docs.
- `snapshot_length_mm/width_mm/height_mm = 0` are IMP-1 sentinel-0 values (variant has no physical dims set yet). Not relevant to draft generation.
- `status_history` is in **chronological order**, oldest at the bottom interestingly (manual creation event = `from_status: "none"`).
- `platform_fee = null` — Shopify orders don't always have platform fee populated.
- `warnings: []` is the MAT-4 operational-warnings channel (currency mismatch, partial BOM coverage). Empty for read-only access.
- Top-level `OrderResponse` does **NOT** include `attachments` nested — those come from a separate endpoint, see D below.

---

## D. AttachmentResponse — Pydantic schema + real response

**Schema** (`backend/schemas/attachment.py`, entire file):

```python
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from models.attachment import AttachmentType


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    uploaded_by_id: uuid.UUID
    file_name: str
    original_name: Optional[str] = None     # ⚠️ ZOMBIE FIELD — see note below
    file_size: int
    mime_type: str
    attachment_type: AttachmentType
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

**`AttachmentType` enum** (`backend/models/attachment.py:19-22`):
- `MOCKUP` = `"mockup"` — **generated DXFs land here per [master rule 4]**
- `REFERENCE` = `"reference"` — **customer ID photos per [master rule 12]**
- `OTHER` = `"other"` — default fallback

**Real response** — `GET /api/attachments/order/fcafdf00-2db5-4399-94dd-5db8b80761fb`:

```json
[
    {
        "id": "bc862371-a657-45e2-b9fe-d8eb978240ca",
        "order_id": "fcafdf00-2db5-4399-94dd-5db8b80761fb",
        "uploaded_by_id": "99c13e1d-3e7b-4a45-9759-adbed5ec9b33",
        "file_name": "IMG_2681.JPG",
        "original_name": null,
        "file_size": 2473586,
        "mime_type": "image/jpeg",
        "attachment_type": "mockup",
        "created_at": "2026-04-25T17:11:54.840662Z"
    }
]
```

**Important notes:**

1. **`original_name: null` — always.** This field is in the Pydantic schema but **NOT in the SQLAlchemy model** (`backend/models/attachment.py`). Zombie field, never populated. **`file_name` IS the original filename** (per `attachments.py:68` — `file_name = file.filename or "unknown"`). Don't be confused.
2. **File size 2.36 MB** for this real JPEG ID-card-style photo. Within `MAX_UPLOAD_BYTES = 50 MB` (`backend/services/file_storage.py:15`).
3. **`attachment_type: "mockup"` here** but for production idlaser flow, **customer photos must be `REFERENCE`** per [master rule 12]. This particular file was uploaded ad-hoc as MOCKUP for testing.
4. **Endpoint returns `list[AttachmentResponse]`** — empty list `[]` if no attachments, not a 404. Order-existence check is implicit.
5. **Physical file path on disk:** `/app/uploads/fcafdf00-2db5-4399-94dd-5db8b80761fb/{file_uuid4}_IMG_2681.JPG` (file_storage.py:33-42 puts files in per-order subdir with UUID-prefixed filename).
6. **DB stores `file_path` as relative**: `{order_uuid}/{file_uuid4}_{original_filename}`.
7. **Attachment endpoints** (`backend/routers/attachments.py`):
   - `POST /api/attachments/order/{order_id}` — multipart upload (file + attachment_type Form)
   - `GET /api/attachments/order/{order_id}` — list (shown above)
   - `GET /api/attachments/{attachment_id}` — download (FileResponse, auth-gated, path-traversal-safe)
   - `DELETE /api/attachments/{attachment_id}` — owner OR uploader only

**For idlaser_service.py**, reading photo bytes:

```python
from services.file_storage import get_absolute_path
abs_path = get_absolute_path(attachment.file_path)  # returns Path | None
if abs_path is None:
    raise HTTPException(404, "File missing on disk")
with open(abs_path, "rb") as f:
    photo_bytes = f.read()  # sync IO — fine inside asyncio.to_thread
```

---

## E. Screenshot — OrderDetailPanel layout (description, image stays in OrderHub Cowork chat)

The screenshot was captured in OrderHub Cowork chat session (Sergii can forward / re-capture). Description for idlaser planner:

**Top bar:** Title "Heavy Mushroom Keychain" + LAMAMARKA SHOPIFY badge + `ID: 7148183421084` + creation date + **status pill** ("IN PRODUCTION" — orange) + close `×`.

**Layout:** Full-screen Radix `<Dialog>` (~95vw × 90vh) with two columns:

**LEFT column** (2/3 width):
1. **Product inventory** card — items table (qty, unit_price)
2. **Notes from customer** card — text area
3. **Production assets** card ← **GENERATE DRAFT BUTTON LIVES HERE** per [master rule 12]
   - Header: "Production assets" + `[+ Upload file]` button (top-right)
   - Drag-drop zone: upload icon + "Upload Production Files" / "SVG, DXF, PNG or PDF" / "No size limit" label
   - Attachment chips list below (icon, filename, file_size, mime_type, MOCKUP/REFERENCE/OTHER badge, download, delete)
4. **Internal notes** card — text area

**RIGHT column** (1/3 width):
1. **Order status** card — current status + "AUTO-SAVE ACTIVE" indicator
2. **Customer profile** card — name, email, country, [+ Add Email]
3. **Shipping & Logistics** card — address, region, [+ Edit]
4. **Payment summary** card — subtotal, shipping, fees, net

**Generate Draft button placement recommendation** — pair it with `[+ Upload file]` as `[+ Upload file]  [Generate Draft from photo ▾]` (split-button choosing which REFERENCE attachment to use), OR as a distinguished row inside the attachments list when at least one REFERENCE exists. Per [master rule 12], button is **enabled iff** order has ≥1 `REFERENCE` attachment.

---

## F. Critical observations for cross-repo coordination

### F.1 CLAUDE.md is stale in several important places

| Written in CLAUDE.md | Reality |
|---|---|
| "Python 3.11" | Backend Dockerfile = **Python 3.12-slim**. Idlaser venv = Python 3.13.12. **Check if idlaser package has any 3.13-only syntax** — will fail at `pip install -e /idlaser` inside backend container otherwise. |
| "React 18" | Actual `react@^19.2.4` (frontend/package.json:27). |
| "Routers: orders, shops, dashboard, imports, users, auth, shipping, mcp" | Actually also: finance, partner_payouts, attachments, products, packaging, materials, overhead_materials, customers. |
| "Sprints 1–10 + UI Modernization complete" | Plus: Phase 3 (MAT-1..5), FIN-1, PART-1, NP-ROBUSTNESS-1, PART-1-fu-1 (closed yesterday). |
| "Dev server on :5173" | Actually **:3000** (saw it live during smoke). |
| Line 60: "Order status mutations are logged in `order_audit_history` table" | **Actual table name is `order_status_history`**; model `OrderStatusHistory` at `backend/models/order.py:255`. CLAUDE.md misnamed it. |

**Use `docs/AI_ONBOARDING.md`, `implementation_plan.md`, and live code as authoritative.** CLAUDE.md is mostly intent + style guide; details are stale.

### F.2 Recent in-flight work (just landed)

- **PART-1** (commit `bd6e528`) — Partner Payouts monoblock. Two new models, 9-endpoint router, frontend section in ShopFinancePage. Not idlaser-related but establishes pattern parity: "two-table model + service + router + 8 frontend components + tests".
- **PART-1-fu-1** (commit `93f45ca`) — **`<ConfirmDialog>` primitive** at `frontend/src/components/ui/ConfirmDialog.tsx`. **Use this** for any "Cancel pipeline?" / "Discard draft?" / "Retry?" prompts in DraftGenerator modal. Props: `isOpen / onClose / title / body / confirmLabel / confirmVariant / onConfirm / isLoading`. Loader2 spinner when isLoading, ESC + outside-click short-circuited during isLoading.
- **MAT-5 Phase B** — `Order.computed_production_cost` is now populated server-side on SHIPPED transition.

### F.3 Pattern verifications vs master contract assumptions

- ✅ **`asyncio.to_thread` confirmed available** — no `BackgroundTasks` / `celery` / `RQ` anywhere in repo (grep clean). [master rule 5] correct.
- ✅ **`sse-starlette==2.2.1`** in `backend/requirements.txt:31` but **NOT used user-facing** — only `mcp.py` uses raw `StreamingResponse(media_type="text/event-stream")` (and `mcp.py` is locked per CLAUDE.md gotcha). Idlaser establishes the first user-facing SSE pattern. **Suggest using `sse-starlette.EventSourceResponse`** rather than raw StreamingResponse — cleaner contract, automatic heartbeat support, ping for connection liveness.
- ✅ **Frontend `@microsoft/fetch-event-source` needed** [master rule 15] — JWT lives in Axios in-memory closure (not localStorage, not cookies, not sessionStorage — verified). Native EventSource can't send custom Authorization headers; query-param JWT would leak in server logs. The library is the right answer.
- ✅ **`UUIDPrimaryKeyMixin + TimestampMixin`** pattern at `backend/models/base.py`. Used everywhere. `IdlaserDraftJob` should mirror exactly: `class IdlaserDraftJob(Base, UUIDPrimaryKeyMixin, TimestampMixin)`.
- ✅ **No `services/order_audit_service.py`** — status history writes are inline at `services/order_service.py:148, 254, 323` (pattern: `db.add(OrderStatusHistory(...))`). [master rule 11] correct that no generic audit log infra exists.
- ⚠️ **Generated DXF naming** — [master rule 4] says `draft_{job_id}.dxf` but `file_storage.save_file()` prepends `{file_uuid4}_` automatically (`file_storage.py:38`). Real on-disk filename = `{file_uuid4}_draft_{job_id}.dxf`. Stored relative path in DB = `{order_uuid}/{file_uuid4}_draft_{job_id}.dxf`. Match this in your CRM service code.
- ⚠️ **`AttachmentResponse.original_name` is zombie** (see D #1). Don't rely on it.

### F.4 Frontend conventions (settled)

- Component placement: `frontend/src/components/orders/draft/` for new directory (mirrors existing `detail/` sibling).
- Hook naming: `useDraftJob.ts` aligned with existing `useOrderDetailController.ts` (`frontend/src/hooks/`).
- API client placement: `frontend/src/api/draftJobsApi.ts` aligned with `attachments.ts`, `orders.ts`, etc.
- Types: TypeScript types live in `frontend/src/types/` (e.g., `UserRole` enum). Draft job types should mirror backend Pydantic.
- Modal pattern: all use `@/components/ui/dialog` (shadcn → Radix Dialog). Props convention: `isOpen / onClose / onSubmit / isLoading`.
- Toast pattern: `useToastStore.addToast(message, 'success' | 'error')` from `@/components/ui/Toast`. Bottom-right transient.
- Loading state: Lucide `<Loader2 className="animate-spin" />` on buttons during async work.
- Empty-state copy is short, in-app voice ("No notes from customer", "No files attached to this order yet" — not "—" / not "No data").

### F.5 Browser-MCP friction patterns (relevant for smoke testing your sprint)

- **Native `window.confirm()` blocks browser-MCP automation** (the reason PART-1-fu-1 happened — see commit `93f45ca`). Use the new `<ConfirmDialog>` primitive — Cowork can click it directly. Don't introduce new native `confirm()` calls in the draft flow.
- The DraftGenerator modal **will be Cowork-smoke-tested via browser MCP**. Make sure SSE events drive observable DOM changes (text content, step badge states, progress %) — Cowork can't introspect React state directly, only render output.

### F.6 task.md state

`task.md` at OrderHub repo root currently contains **PART-1-followup-1 spec (just-closed)**. Per `docs/AI_ONBOARDING.md` §9, task.md is rewritten every sprint and intentionally not committed between sprints. **OrderHub-side Cowork will rewrite it for S004 next** before handing to CC session B. Don't read current `task.md` as authoritative for S004.

### F.7 Open Architectural Questions (parked) — none conflict with S004

`implementation_plan.md` after deferred table lists 2 parking-lot items:
- **Shop-level region anchor** — `Shop` has no country/region/currency. Not blocking idlaser.
- **Multi-warehouse evolution** (post-PKG-1b) — single warehouse today. Not blocking idlaser.

### F.8 Hard contradictions vs master contract — none

Re-read 15 Behaviour rules. **No contradictions with CRM reality.** All 15 settled rules implementable as written. 10 OQs adresseable from CRM code with file:line evidence.

### F.9 Suggested coordination mechanism going forward

This file (`docs/cross-project/idlaser-S004-coordination.md` in OrderHub repo) is the first cross-repo coordination artifact. Suggest:
- For ongoing coordination: append-only handoff section at the bottom of this file, OR symmetric file in idlaser repo with rsync/git-cross-link. Sergii becomes "ping the other side" instead of copy-paste courier.
- For shared design assets (event schemas, response types): keep them as a single source of truth in `idlaser/task.md` (the master contract), reference from both sides.
- This file does NOT need to be committed to OrderHub git history if it's purely transient — Sergii's call.

---

## What OrderHub-side Cowork is doing next

1. **Will rewrite `task.md` for S004 CC session B** — adapting master contract Scope into OrderHub-specific file paths, answering OQ 4/5/6/8/9/10 with file:line evidence, adding CRM-side OQs (exact SQLAlchemy patterns, migration naming, frontend placement), planning commit split per master §Workflow.
2. **Will add the diagnostic prefix** to CC session B's prompt per your brief.
3. **Cross-questions raised here** for idlaser-side acknowledgement:
   - Python 3.12 vs idlaser's 3.13 venv — are there any 3.13-only syntax features (PEP 695 type aliases without `from __future__`, etc.) in idlaser package code that would fail under Python 3.12?
   - `sse-starlette.EventSourceResponse` vs raw `StreamingResponse` for the CRM-side SSE — any preference from your side?

End of coordination package.
