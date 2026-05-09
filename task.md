# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Current task:** _(none — awaiting next assignment)_
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

_No active task. See [implementation_plan.md](implementation_plan.md) → Active Roadmap for the unified backlog._

**Next on deck:** **BUG-5** — blank-SKU dedup by Variations in the Etsy CSV
importer. Listing 4343151753 in LeatherCraft UA currently has 5 catalog
variants where it should have 2; root cause is `_compute_effective_sku`
generating per-row counters instead of grouping by `(listing_id,
Variations)` for blank-SKU rows. After BUG-5 lands, wipe + reimport of
LeatherCraft UA orders/products to rebuild the catalog cleanly.
