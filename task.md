# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks. 
> 
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Architectural Audit:** Refer to [REPORT_2026_04_21.md](docs/audit/REPORT_2026_04_21.md).
> 
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

## Current Session: Documentation Cleanup & Handover
- [x] Consolidate architecture visuals into `implementation_plan.md`
- [x] Create `backend/models/product.py`
    - [x] `Product` model
    - [x] `ProductVariant` model with `volume_cm3` hybrid property
- [x] Create `backend/models/packaging.py`
    - [x] `PackagingType` enum
    - [x] `PackagingBox` model
- [x] Update `backend/models/order.py`
    - [x] Add `OrderItem` snapshot columns
    - [x] Add `Order` computed fields
- [x] Update `backend/models/__init__.py` (export new models)
- [x] Generate and verify Alembic migration
    - [x] Generate migration
    - [x] Test on SQLite (Tested on Postgres with roundtrip verification)
    - [x] Verify `packaging_boxes` is empty
- [x] Run existing tests to ensure zero regressions (Smoke test passed)
- [x] Frontend: Add parcel parameters (weight/volume) to `DetailLogistics.tsx`
- [x] Frontend: Add TTN deletion button with confirmation to `DetailLogistics.tsx`
- [x] Frontend: Update `OrderDetailPanel.tsx` to integrate delete functionality
