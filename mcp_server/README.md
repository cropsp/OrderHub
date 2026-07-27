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

All read-only in this release.

| Tool | Reads |
|---|---|
| `list_shops` | shops the agent may access |
| `list_materials` / `get_material` | direct materials + weighted-average unit cost + stock |
| `list_material_receipts` | purchase history (what moves the weighted average) |
| `list_material_movements` | the append-only stock ledger |
| `list_overhead_materials` / `list_overhead_expenses` | indirect costs |
| `list_products` / `get_product` | catalog + variants |
| `get_product_bom` | a product's recipe + per-line costs |
| `compute_product_cost` | recompute a product's cost from current material prices |

Writes (receipts, BOM editing, overhead expenses) land in the next step.

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
