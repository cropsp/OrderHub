# Partner Payouts — Current Live Rules (PARTNER-CONFIG-1)

**Status:** describes the state of `main` (merged + deployed 2026-08-07). Extracted verbatim from CLAUDE.md § Gotchas on 2026-08-21 (docs restructuring; content unchanged, only re-sectioned).
**Read this BEFORE touching** partners, `shop_partner_config`, settlements, platform fees, or anything feeding a partner base.
**Authoritative history + full amendment list:** `implementation_plan.md` → PARTNER-CONFIG-1 (requirement, decisions ①–④, review amendments ⑤–⑫). Older design docs (`partner-payouts.md` = PART-1 era, `profit-definition.md` §6) are partially superseded — see the banner in `profit-definition.md`.

## 1. Entities and editing surface

Partners are a **global entity** (`partners`) + per-shop config in `shop_partner_config` (percent, basis, settlement currency), edited in the shop editor's Partners tab, **OWNER-only**.

## 2. Settlement bases

`TURNOVER` and `PROFIT` — both net of discounts, both deduct refunds **dated in the period** (Model 2), and both **exclude shipping economics entirely** (`docs/design/profit-definition.md` §6 rationale; PROFIT ≠ the Finance-page net profit, which nets shipping — see `NETPROFIT-RECONCILE`). Legacy enum values `REVENUE_ITEMS_MINUS_FEES` / `NET_PROFIT_PRODUCT_ONLY` deserialise but are not selectable for new configs.

## 3. Settlement lifecycle invariants

- Settlements/payments stay **immutable post-create**.
- Overlapping periods per (shop, partner) are **hard-blocked server-side** (`_overlap_predicate`, closed-interval).
- Negative bases produce negative settlements by design.

## 4. FX

UAH terms (in practice: allocated overhead) convert via `fx_service.resolve()` at Calculate time and the rate freezes onto `PartnerSettlement.fx_rate_used` — no usable rate is a loud 422, never a dropped term. Unallocated (NULL-shop) overhead never enters a partner base.

## 5. Audit

Partner-config changes audit to **`partner_config_audit`** (NOT `access_audit` — its `target_user_id` means "whose access changed"; a partner is not a user), and partner entities must not be hard-deleted while audit rows reference them.

## 6. Migration rule (standing)

`PartnerSettlementFormula` is a **PG enum**; the PARTNER-CONFIG-1 migration docstring carries a standing rule that no future migration may write the two new values in its own transaction (PG16 same-transaction restriction — hence no `server_default`/CHECK on `shop_partner_config.basis`).

## 7. Fee backfill

`POST /api/shops/{shop_id}/backfill-platform-fees` (OWNER-only, `dry_run` first, never overwrites a non-NULL fee, skips CANCELLED, reports `overlapping_settlements`).
