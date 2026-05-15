# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **NP context:** [docs/integrations/nova-poshta.md](docs/integrations/nova-poshta.md) for the NP API contract, gotchas, and history of NP-* sprints.
> - **Current task:** NP-ROBUSTNESS-1 — bundle of 2 NP reliability fixes (NP-UX-2 + NP-FIX-3b)
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

## NP-ROBUSTNESS-1 — NP idempotent delete + sender phone validation

### Goal

Bundle of 2 medium-effort parked items that improve **operational reliability** of the Nova Poshta integration. Both items affect KoraKlenu's shipping workflow (the only NP-using shop today). Per priority assessment: NP is the operational backbone for KoraKlenu; failures here cause real workflow disruption (manual SQL fixes, blocked TTN flows). Closing both in one bundle because they share the same surface area (`routers/shipping.py` + Edit Store Settings → Logistics modal) and tests overlap.

**Item 1 — NP-UX-2: idempotent TTN delete.** Today, if an operator deletes a TTN through the NP cabinet manually (e.g. testing a shipment, then cancelling it before pickup), `OrderHub`'s Delete TTN button **fails permanently with HTTP 400** because `routers/shipping.py:delete_np_ttn` treats any NP API error as fatal — it rolls back the transaction, leaving `Order.ttn_number` stale. The operator must fix this via SQL. Fix: catch the specific NP error message(s) for "already deleted" / "not found" and treat them as **effective successes** — clear the local TTN reference anyway. Eventual consistency, not a sync gap.

**Item 2 — NP-FIX-3b: sender phone validation.** The Sender Phone input on Edit Store Settings → Logistics (NP) modal accepts arbitrary text. An operator once entered a surname there and it propagated all the way into the NP `InternetDocument.save` payload, where NP rejected it with "SendersPhone invalid format" — silently breaking ALL TTN creates from that shop until noticed. Two-part fix: (a) frontend regex/mask on the Phone field (UA mobile pattern), (b) backend normalization in `routers/shipping.py` mirroring the recipient-phone normalization at `lines 175-178` (strip non-digits, prepend `38` if missing). Currently no validation on Sender Name either — left out of scope (different concern, separate fix if needed).

### Behaviour rules (settled — do not relitigate)

1. **Single atomic commit, single sprint.** Both items are NP reliability fixes on overlapping files. Commit message: `fix(np): idempotent TTN delete + sender phone validation/normalization`.

2. **NP-UX-2: detect "already deleted" / "not found" by the specific NP error string(s), not by status code.** NP returns HTTP 200 with `success: false` and an `errors` array/dict regardless of the actual failure mode. The MICRO-CLEANUPS-1 sprint (commit `a48c73e`) already fixed `_post()` to handle dict-shape errors correctly — so the error message strings are now reliably extractable. The fix in `delete_np_ttn` matches against the message strings (case-insensitive) and treats matched cases as success. CC must grep / scan `docs/integrations/nova-poshta.md` for documented "already deleted" / "not found" error message variants; if not documented, accept the literal English strings observed in the wild from NP-FIX-4 closure ("Document already deleted {N}") plus a defensive English-substring check `("already deleted" in msg.lower() or "not found" in msg.lower() or "no document" in msg.lower())`.

3. **NP-UX-2: clear `Order.ttn_number = None` AND emit an audit-log entry on the soft-success path.** The audit log entry should distinguish "TTN deleted via NP" (real success) from "TTN already deleted (cleared local ref)" (soft success) for future debugging. Use the existing audit-log path (whatever PKG-2's `MaterialMovement` or order_status_history pattern uses for system actions); CC to grep.

4. **NP-UX-2: do NOT change packaging-stock idempotency on TTN-delete.** PKG-2's stock_increment hook on TTN-delete fires on "real" success. On the new soft-success path, the increment **should still fire** if `order.packaging_id IS NOT NULL` — because semantically the local state is "no TTN exists for this order, packaging units returned to inventory". This is consistent with what would have happened if the NP delete had succeeded directly. Operator records of stock are based on "what TTN delete operations they did in OrderHub", not "what NP server confirmed".

5. **NP-FIX-3b: UA mobile pattern is `380XXXXXXXXX` (12 digits, starts with 380) OR `0XXXXXXXXX` (10 digits, starts with 0).** Backend normalization rule:
   - Strip all non-digit characters.
   - If result starts with `380` and is 12 digits → keep as-is.
   - If result starts with `0` and is 10 digits → replace leading `0` with `380` (so `0991234567` → `380991234567`).
   - If result is 9 digits (operator entered without leading 0 or country code) → prepend `380` (so `991234567` → `380991234567`).
   - Else → 422 validation error: *"Sender phone must be a Ukrainian mobile number (e.g. 380XXXXXXXXX or 0XXXXXXXXX)."*
   
   Frontend regex: `/^(\+?380|0)?\d{9}$/` (after stripping non-digits) to accept the same range of inputs as backend, with same error message. Backend is the source of truth; frontend regex is a UX-friendliness layer.

6. **NP-FIX-3b: apply normalization in BOTH places.** Frontend prevents bad data entry. Backend normalizes on every save (defensive against API-direct callers and future imports). The backend normalization should run in `routers/shops.py` (or wherever the shop NP credentials are saved) at the moment of write — store the **normalized** value in the DB. Existing data may have invalid phones; backfill via SQL is **NOT** in scope.

7. **NP-FIX-3b: only Sender Phone, NOT Sender Name.** Sender Name validation is a separate cosmetic concern, and the parked item explicitly notes it. Don't expand scope.

8. **No schema changes, no migrations.** Both fixes are pure code changes.

9. **Manual smoke MUST include the live "delete-already-deleted" scenario.** This was the original bug repro from NP-FIX-3a. Manual test: create a TTN through OrderHub UI, manually delete it from NP cabinet, then click Delete TTN in OrderHub — must succeed cleanly and clear the local ttn_number. Without this live verification, we don't know if the fix actually works (NP cabinet manipulation is hard to mock).

### Scope

- **In scope, backend:**
  - **`backend/routers/shipping.py:delete_np_ttn`** — wrap the NP API call in a try/except block (or check the response) for the soft-success error messages per behaviour rule #2. On soft-success: log the audit entry per rule #3, clear `Order.ttn_number = None`, fire the packaging-stock increment per rule #4, return 200 with a friendly response indicating the soft-success path was taken (e.g. `{"status": "soft_success", "message": "TTN was already deleted on NP side; local reference cleared.", "warnings": [...]}`).
  - **`backend/routers/shops.py` (or wherever shop NP credentials are persisted)** — backend normalization on Sender Phone per rule #5. Apply on PATCH/PUT save. Use a small helper function like `normalize_ua_phone(raw: str) -> str` that returns the normalized form OR raises `HTTPException(422, ...)` per rule #5's error message. Place the helper in a sensible utils module (CC: grep for existing phone-normalization helpers — `routers/shipping.py:175-178` already has recipient-phone normalization; either reuse that helper if extracted, or extract it now to a shared `services/phone_normalization.py`). 
  - **Backend tests** in `backend/tests/`:
    - Extend `test_shipping_router.py` (or wherever `delete_np_ttn` tests live): 2 new tests — (a) NP returns "Document already deleted {N}" → assert response is soft-success, `Order.ttn_number` is cleared, packaging increment was applied; (b) NP returns "No document found" → same soft-success behavior.
    - Extend `test_shops_router.py` (or wherever shop credential save tests live, OR create new `test_phone_normalization.py` for unit tests of the helper): 4 new tests for the normalization helper — (a) `380991234567` → `380991234567`; (b) `0991234567` → `380991234567`; (c) `991234567` → `380991234567`; (d) `Іван Петренко` → 422.
    - Total expected: 143 → ~149 (+6).

- **In scope, frontend:**
  - **`frontend/src/components/shops/EditStoreSettingsModal.tsx` (or wherever the Logistics (NP) tab's Sender Phone field lives — CC to grep)** — add a regex validator on the Sender Phone field: `/^(\+?380|0)?\d{9}$/` after stripping non-digits. On invalid input, show inline error: *"Phone must be a Ukrainian mobile number (e.g. 380991234567 or 0991234567)."* Disable Save button while invalid.
  - **TTN-delete success path on order detail** — extend the existing toast handler to read the new `status: "soft_success"` response shape and surface the friendly message: *"TTN was already deleted on NP side; local reference cleared."* (Info-style toast, neutral, not error.) Real success keeps the existing success toast.
  - **Frontend tests:**
    - Extend test for the Edit Store Settings modal (file path TBD by CC's grep): 2 new vitest cases — invalid input shows error, valid input enables Save.
    - Extend test for the TTN-delete handler: 1 new case — soft-success response surfaces the info toast instead of error.

- **Out of scope (do NOT touch):**
  - Sender Name validation — explicitly noted in the parked item, separate concern.
  - Recipient phone normalization — already exists at `routers/shipping.py:175-178`, untouched.
  - PKG-2's packaging stock_increment hook — fires per rule #4 on soft-success too, but the hook itself is unchanged.
  - NP credentials storage / encryption — out of scope, preserved as-is.
  - Other NP error scenarios beyond "already deleted" / "not found" — keep current fatal-error behavior. We're only soft-success-ing the specific delete-idempotency case.
  - Backfill of existing shop sender phones — SQL the operator can run if needed.
  - `Order.audit_history` schema or pattern changes.
  - Fixing other lurking NP bugs (e.g. payload validation issues other than phone) — if discovered, file as separate parked items.

### Open questions for the planner

CC must answer each in the plan with cited grep evidence (file:line refs).

1. **Exact NP "already deleted" / "not found" error message strings.** Read `docs/integrations/nova-poshta.md` for documented variants. Also read `implementation_plan.md` NP-FIX-4 closure for the "Document already deleted {N}" string mentioned in the wild. State the chosen substring matches in the plan.

2. **Existing recipient-phone normalization helper at `routers/shipping.py:175-178`.** Grep that area. Is it inline or already extracted to a helper? If inline → CC's call: extract to `services/phone_normalization.py` now (DRY) or replicate inline (simpler). State the choice with rationale.

3. **Sender Phone field location in frontend.** Grep for `senderPhone`, `sender_phone`, `Sender Phone` across `frontend/src/components/`. Identify the file:line of the input element + any existing validator. Confirm the modal name and edit-mode flow.

4. **TTN delete response shape contract.** What does `delete_np_ttn` currently return on success? On error? Grep `delete_np_ttn` and identify the response model. CC's plan must state the new response shape for soft-success and confirm it's backwards-compatible with the existing frontend handler (or list the frontend changes needed).

5. **Audit log pattern for "TTN already deleted (soft-success)".** What's the existing audit-log shape for system-driven order changes? Is there an `Order.audit_history` table? Grep `audit_history` or similar in `backend/models/`. State the audit entry shape that will be written on soft-success.

6. **`packaging_id IS NOT NULL` guard on TTN-delete stock increment.** Grep the existing TTN-delete handler. Verify the stock-increment fires unconditionally on real-success when `packaging_id` is set. The new soft-success path mirrors this exactly.

### Verification

- **Backend gates:**
  - `cd backend && python -m pytest tests/ -v` — expect 143 → ~149 passing (+6 new).

- **Frontend gates:**
  - `cd frontend && npx tsc --noEmit` — clean.
  - `cd frontend && npm run lint` — clean for touched files.
  - `cd frontend && npm run test -- EditStoreSettings` — new cases pass (file name TBD).

- **Manual smoke (Cowork via browser MCP, after Sergii approves — and per behaviour rule #9):**
  1. **Pre-flight (Sergii):** ensure KoraKlenu has a SHIPPED order with TTN already created. If no such order exists, create a fresh test order with KoraKlenu shop, NEW status, trigger Generate NP Label to create a TTN.
  2. **Sender phone validation flow:**
     - Open Edit Store Settings modal for KoraKlenu → Logistics (NP) tab.
     - Try entering invalid phone like "Сергій" or "abc123" → frontend shows inline error, Save button disabled.
     - Try entering `0991234567` → frontend accepts, Save enabled. Save → backend normalizes to `380991234567`, stored value reflects normalization.
     - Try entering `380991234567` directly → accepted, stored as-is.
     - Try entering `+380 99 123-45-67` → stripped to `380991234567`, normalized, stored.
  3. **Idempotent delete flow (the critical one):**
     - Open the TTN-equipped KoraKlenu order in OrderHub.
     - Open NP cabinet in another tab/window. Find the same TTN. Manually delete it from NP cabinet.
     - Return to OrderHub order detail. Click Delete TTN button.
     - **Before fix:** would error out with 400, ttn_number persists.
     - **After fix:** should succeed with info toast *"TTN was already deleted on NP side; local reference cleared."* Order's `ttn_number` is now NULL. If `packaging_id` was set, packaging stock incremented (verify on `/inventory/packaging`).
  4. (If time permits) **Real-success delete:** create another TTN (now you can, sender phone is fixed). Delete it through OrderHub UI directly (not via NP cabinet first). Should work as before — success toast, ttn_number cleared, packaging incremented.
  5. Console clean throughout.

### Workflow

- **Plan mode REQUIRED** — both items have non-trivial decisions (error string matching, audit log pattern, response shape backward compatibility). The 6 OQs need real grep evidence.
- The plan MUST:
  - Read `docs/integrations/nova-poshta.md` for NP error contract.
  - Read MICRO-CLEANUPS-1 closure (commit `a48c73e`) to understand the dict-shape error fix that just landed — make sure the new soft-success matching reads errors correctly post-fix.
  - Answer all 6 Open Questions with cited file:line evidence.
  - Show the `delete_np_ttn` patch (real code, not pseudo) including the soft-success branch + audit log + packaging-stock decision.
  - Show the `normalize_ua_phone` helper signature + key body fragments (the 4 normalization branches per rule #5).
  - Show the new TTN-delete response shape + frontend handler change needed.
  - Confirm out-of-scope files won't be touched.
  - State expected pytest delta.
- **No code edits until Sergii approves the plan.**
- After approval: edits → backend pytest → frontend gates → **MANUAL SMOKE INCLUDING THE LIVE NP CABINET TEST** → commit.
- Commit: `fix(np): idempotent TTN delete + sender phone validation/normalization`
- Do **NOT** update `implementation_plan.md` or `task.md` post-fix notes — Cowork writes those after smoke verification.
- **No Co-Authored-By or Claude trailer** (AI_ONBOARDING.md §9).
