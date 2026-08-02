# OrderHub MCP Server

Lets an AI agent manage OrderHub's warehouse and product catalog on the owner's
behalf — read materials, receipts, stock ledgers, recipes (BOMs) and product
costs, conversationally.

It is a **separate local process**, not part of the FastAPI app. It talks to
OrderHub over its own REST API and imports nothing from `backend/`.

## Why it is built this way

| Decision | Reason |
|---|---|
| Talks REST, not Python imports | Every call travels the same routers as the UI, so the shop-scope guard, the capability guard and `test_money_field_completeness` / `test_route_scope_completeness` all keep covering the agent. There is deliberately no second write path. |
| Its own venv | The MCP SDK needs `pydantic>=2.11`; the backend is pinned to `2.10.4`. Separating them means this can track the SDK without forcing a pydantic upgrade across every schema in the running app. |
| stdio transport | Runs on the operator's machine, spawned by the MCP client. OrderHub gains no new public surface — no ingress, no Cloudflare Access exception, nothing added to the tunnel. |
| A MANAGER agent user, never OWNER | OWNER short-circuits `get_shop_scope` and `get_capabilities`, which would make the agent unbounded. A MANAGER with explicit grants is bounded by the guards that already bound a human manager. |

Superseded `backend/routers/mcp.py`, which had never worked (three API mismatches
against its pinned SDK) and gated only the connection, not the tools.

## Setup

**1. Install**

```bash
python3 -m venv mcp_server/venv
mcp_server/venv/bin/pip install -r mcp_server/requirements.txt
```

**2. Create the agent user** (idempotent; safe to re-run)

```bash
cd backend && source venv/bin/activate
python scripts/provision_agent_user.py --shops KoraKlenu "Lamamarka Shopify"
```

Grants exactly the shops you name (the list is authoritative — omitted shops are
revoked) plus the `view_costs` capability. `view_finance` stays off: the agent
writes costs, it has no reason to read the P&L. Use `--all-shops` to grant
everything, `--show` to print current state, `--reset-password` to reissue.

The password is printed **once**. Store it in step 3.

**3. Configure**

```bash
cp mcp_server/.env.example mcp_server/.env   # .env is git-ignored
# paste the password into ORDERHUB_AGENT_PASSWORD
```

**4. Register with your MCP client**

```json
{
  "mcpServers": {
    "orderhub": {
      "command": "/home/serhii/projects/OrderHub/mcp_server/venv/bin/python",
      "args": ["/home/serhii/projects/OrderHub/mcp_server/main.py"],
      "env": {
        "ORDERHUB_API_URL": "http://localhost:8000",
        "ORDERHUB_AGENT_EMAIL": "agent@orderhub.dev",
        "ORDERHUB_AGENT_PASSWORD": "…"
      }
    }
  }
}
```

The `env` block is an alternative to `mcp_server/.env` — use whichever you
prefer, but put the password in exactly one of them. Point `ORDERHUB_API_URL` at
`https://orderhub.orderapp.uk` to work against production.

## Tools

Warehouse and catalog only. Orders, shipping, users, shops and finance are
deliberately absent — every one has irreversible real-world side effects.

**Read**

| Tool | Reads |
|---|---|
| `list_shops` | shops the agent may access |
| `list_materials` / `get_material` | direct materials + weighted-average unit cost + stock + supplier article (`search` matches name **or** article) |
| `list_material_receipts` | purchase history (what moves the weighted average) |
| `list_material_movements` | the append-only stock ledger |
| `list_receipts_by_invoice` | every line of one supplier invoice — direct materials **and** overhead, no total |
| `list_overhead_materials` / `list_overhead_expenses` | indirect costs |
| `list_products` / `get_product` | catalog + variants |
| `get_product_bom` | a product's recipe + per-line costs |
| `compute_product_cost` | recompute a product's cost from current material prices |

**Write**

| Tool | Does |
|---|---|
| `create_material` | new direct material (currency locked at creation; refuses a duplicate article or name) |
| `update_material` | name, unit, supplier, supplier article, notes, low-stock threshold, waste % |
| `archive_material` | discontinue (soft delete; history preserved) |
| `record_material_receipt` | book a purchase — **this is what sets cost** |
| `adjust_material_stock` | stocktake correction or waste, no cost change |
| `create_overhead_material` / `record_overhead_expense` | indirect costs |
| `set_product_bom` | replace a whole recipe (guarded, see below) |
| `add_bom_line` / `remove_bom_line` | change one recipe line, preserving the rest |

Quantities and money are decimal **strings** ("5.00", "597.14") end to end —
binary floats do not round-trip cents.

### Safety rails

- **BOM wipe protection.** `PUT /bom` is delete-all + reinsert with no audit and
  no undo. `set_product_bom` refuses any call that would remove or change
  existing lines unless `confirm_replace=True`, and the refusal shows exactly
  what would be lost. `add_bom_line` / `remove_bom_line` read the current recipe
  and change only the line you name, so they cannot wipe anything.
- **Duplicate materials.** An exact name collision is refused with the existing
  material's id — two rows for one real material split the weighted average
  permanently. Override with `allow_duplicate_name=True`.
- **Append-only reality.** Receipts and stock movements cannot be edited or
  deleted. A mistake is corrected by another receipt or an adjustment, and both
  stay in the ledger.

### Action log

Every write reports itself to `agent_action_log`: tool, arguments, outcome, and a
human-readable summary ("Unit cost 10.0000 -> 15.0000; stock 100.00 -> 200.00").
The domain tables record *what changed*; this records what the agent meant,
which is what makes "undo what the agent did on Tuesday" answerable.

Review it as the owner:

```
GET /api/agent-actions?ok=false        # everything the agent got rejected on
GET /api/agent-actions?tool=set_product_bom
```

Rejected API calls are logged too. Calls stopped by the guards above are not —
nothing was attempted, and you already saw the refusal in the conversation.

## Auth and revocation

Logs in once as the agent user, keeps the httpOnly refresh cookie, and mints a
fresh 15-minute access token whenever one expires. The password is only sent
again if the 30-day refresh token lapses.

**To revoke:** set the agent user inactive. Both `get_current_user` and
`/api/auth/refresh` check it, so access dies within 15 minutes.

```sql
UPDATE users SET is_active = false WHERE email = 'agent@orderhub.dev';
```

An `api_keys` table (real revocation list, last-used tracking) is filed as a
precondition for ever exposing this remotely.

## Known limits

- **UAH materials do not cost USD orders.** The production-cost snapshot written
  when an order ships is skipped when the material currency differs from the
  order currency, so today's UAH materials produce a booked cost for KoraKlenu
  only. Lamamarka and the Etsy shops keep their manual per-order cost until the
  planned `FX-CONVERSION` work lands. Accepted knowingly — the warehouse data is
  the value here.
- **Costing is forward-only.** The snapshot is written at the SHIPPED transition,
  so orders already shipped keep a null computed cost even after recipes exist.
- **Product `cost_price` is not exposed.** It feeds no cost computation anywhere
  in the app — materials and BOMs are the real COGS path.

## Tests

```bash
cd mcp_server && venv/bin/python -m pytest tests/ -q
```

Covers the auth lifecycle (401 retry, single re-auth under concurrency, revoked
agent fails fast), error passthrough (a 403 must reach the agent as a readable
permission error), and that every tool maps to its endpoint and issues only GETs.
