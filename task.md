# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Current task:** _(none — Round 2 complete; Round 3 NP-DISC complete; awaiting NP-FIX-2)_
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

_No active task._

**Round 2 (Imports auto-populate catalog) — fully shipped:** UX-1, IMP-1,
BUG-5, IMP-2, BUG-8 + the BUG-9 scheduler regression caught during NP audit.

**Round 3 — Nova Poshta initiative:**
- **NP-DISC** complete. Deliverable:
  [docs/integrations/nova-poshta-audit-2026-05.md](docs/integrations/nova-poshta-audit-2026-05.md).
  All 5 open questions answered and locked in §7.
- **Next on deck: NP-FIX-2** — pytest infrastructure for the NP service
  + router. Mocks `httpx.AsyncClient`, exercises every existing
  `NovaPoshtaClient` method and every `routers/shipping.py` endpoint
  without touching real NP. Hard prerequisite for every subsequent
  NP-FIX-* sprint.

After NP-FIX-2 and NP-FIX-1 land, the user manually creates a dev shop
on a personal NP account (NP-FIX-3, ~15-20 min, no code) before
NP-FIX-4 onwards.

See `implementation_plan.md` → Active Roadmap and the audit doc §6/§8
for the full prioritized fix list.
