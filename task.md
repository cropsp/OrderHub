# AI Agent Task List (Session Level)

> [!IMPORTANT]
> **To all AI Agents:** This file is a **session-level checklist** for immediate technical tasks.
>
> - **Strategic Roadmap & History:** Refer to [implementation_plan.md](implementation_plan.md).
> - **Current task:** _(none — NP-FIX-2 complete; awaiting NP-FIX-1)_
>
> DO NOT store long-term plans here. Only active, atomic steps for the current session.

---

_No active task._

**NP-FIX-2 done** — 97/97 tests, zero production code change, regression
net in place for the rest of NP-FIX-* work.

**Next on deck: NP-FIX-1** — sender-warehouse validation. Backend
rejects with 400 when `shop.np_sender_city_ref` or
`shop.np_sender_warehouse_ref` is unset. Closes the original
courier-dispatch incident.

After NP-FIX-1, the user manually creates the dev shop on a personal
NP account (NP-FIX-3, ~15-20 min, no code) before NP-FIX-4 onwards.

See `implementation_plan.md` → Active Roadmap and the audit doc §6/§8.
