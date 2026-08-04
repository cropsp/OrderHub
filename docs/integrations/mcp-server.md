# MCP Server — operations & connection runbook

> **Status (2026-07-27): LIVE, superseded rewrite.** The old SSE server in
> `backend/routers/mcp.py` was **deleted** — it never worked (three API mismatches vs its
> pinned SDK, tool-layer auth absent). The current MCP server is a **separate local stdio
> process** at `mcp_server/`, a warehouse/catalog agent. Built on branch `feat/mcp-warehouse`.
>
> **Primary usage + tool reference: `mcp_server/README.md`.** This file is the *ops runbook*
> — how to connect on dev, how to roll out to prod, where credentials live. It does not
> duplicate the README.

## What it is (one paragraph)

A stdio MCP server, run locally on the operator's machine, spawned by the MCP client
(Claude Code / Claude Desktop). It exposes ~21 warehouse+catalog tools (materials, receipts,
stock adjust, overhead, BOMs, product cost compute). Every tool call travels the CRM's own
REST API as a dedicated **MANAGER** agent user (`agent@orderhub.dev` on dev), so the existing
shop-scope + capability + money-leak guards all keep covering it — there is deliberately no
second write path. Reads/writes are audited in `agent_action_log`. Full rationale + tool list
+ safety rails: `mcp_server/README.md`.

## Where credentials live (NO secrets in this repo)

- **Master copy → password manager.** The agent user's password (dev and, later, prod) and —
  for prod only — the Cloudflare Access service-token id/secret live **only** in the password
  manager, alongside `ENCRYPTION_KEY`, R2 tokens, etc. Never in git.
- **Local working copy → `mcp_server/.env`** (git-ignored by the repo's global `.env` rule).
  Holds `ORDERHUB_API_URL`, `ORDERHUB_AGENT_EMAIL`, `ORDERHUB_AGENT_PASSWORD` (+ the CF service
  token headers for prod). Created from `mcp_server/.env.example`.
- The password is printed **once** by `backend/scripts/provision_agent_user.py`. Re-issue with
  `--reset-password`; inspect state with `--show` (no secret printed).

## Connecting on DEV (the simple path — start here)

Dev backend is `http://localhost:8000` on the same machine → no Cloudflare Access, no service
token. Use Claude Code in WSL (it spawns the binary directly).

1. `./start-dev.sh` (backend must be reachable when the first tool call fires, not at launch).
2. Agent user already provisioned on dev (`agent@orderhub.dev`, MANAGER, `view_costs`, granted
   KoraKlenu + Lamamarka Shopify). Re-provision / narrow grants:
   `cd backend && source venv/bin/activate && python scripts/provision_agent_user.py --shops KoraKlenu`
3. `cp mcp_server/.env.example mcp_server/.env` → paste the agent password.
4. Register with Claude Code — `.mcp.json` at repo root. **Git-ignored — do NOT commit.** The
   dev entry alone carries no secret, but once the prod entry is added (rollout §D) the file holds
   the prod agent password inline, so it is in `.gitignore` and `chmod 600`.
   ```json
   { "mcpServers": { "orderhub-dev": {
       "command": "/home/serhii/projects/OrderHub/mcp_server/venv/bin/python",
       "args": ["/home/serhii/projects/OrderHub/mcp_server/main.py"],
       "env": { "ORDERHUB_API_URL": "http://localhost:8000",
                "ORDERHUB_AGENT_EMAIL": "agent@orderhub.dev" } } } }
   ```
   (password from `mcp_server/.env`). Or: `claude mcp add orderhub-dev --scope project -- <venv-python> <main.py>`
5. First session — three prompts: "list materials with unit cost + stock"; "record a purchase
   against <material>: 20 dm² at 610 UAH, supplier X, invoice Y"; "what did that do to the
   weighted-average cost?" Then check: `SELECT tool, ok, summary FROM agent_action_log ORDER BY created_at DESC LIMIT 5;`
   Receipts are append-only — use a throwaway material for the very first run if unsure.

## PROD rollout runbook

> **EXECUTED 2026-08-03 — prod MCP is live and verified.** Branch merged to `main` (b570cc5) +
> deployed (backend + **frontend**; all 4 migrations applied at container start, head
> `d90b7c25e4a1`); FX scheduler fetched the live NBU rate on boot. Prod agent provisioned with
> `--all-shops` (the 3 real prod shops). CF service token "orderhub-mcp" (non-expiring) + a
> "Service Auth" Access policy added. `orderhub-prod` registered in `.mcp.json`; `list_shops`
> returns the 3 shops through the full CF-gated path. The steps below are kept as the reference
> for the next environment / re-issue; some specifics (file counts, migration head) are from the
> original MCP-WAREHOUSE-only plan and have since grown.

`mcp_server/` is **not deployed** — it stays on the laptop and is pointed at prod. Prod needs
only the **backend changes** + a prod agent user + the Cloudflare Access path.

**A. Deploy the backend** (13 files, no frontend; rides the image rebuild):
1. Merge `feat/mcp-warehouse` → main, deploy as usual.
2. `docker compose -f docker-compose.prod.yml build backend && up -d backend`, then
   `exec backend alembic upgrade head` → **`f982a7258777`** (additive: `agent_action_log`, 3
   indexes; round-trip verified).
3. `mcp.py` deletion is zero-risk — `/api/mcp/sse` + `/api/mcp/messages` disappear, nothing
   consumed them, they never worked. Reduces public surface.
4. **`products.py` fix is the one user-facing change:** any prod user with `view_costs=false`
   currently gets a **500 on every product read**; after, they get 200 with
   `variants[].cost_price` nulled. Check who's affected:
   `SELECT u.email, u.role, c.capability, c.granted FROM users u LEFT JOIN user_capability c ON c.user_id = u.id WHERE u.role != 'OWNER';`
   If prod is owner-only, this is invisible.

**B. Create the prod agent user** (doesn't exist there; WORKDIR `/app`):
```
docker compose -f docker-compose.prod.yml exec backend \
  python scripts/provision_agent_user.py --all-shops
```
**Prod shops differ from dev:** prod has **Lamamarka (ETSY), Lamamarka Shopify (SHOPIFY),
Vine&Roses ETSY** — there is **no KoraKlenu on prod** (dev-only). All three sell in non-UAH, so
now that `FX-CONVERSION` is live they all book COGS; `--all-shops` grants exactly those three
(re-run with explicit `--shops` later if you'd rather pin the list so a future new shop isn't
granted silently). Prints the prod password once → password manager + the prod entry in
`.mcp.json`. Re-issue with `--reset-password`; `--show` prints state without the secret.

**C. Cloudflare Access** — prod is Access-gated (a `curl .../api/health` returns 302 to login).
So the MCP client needs a **CF Access service token**:
1. `curl -s -o /dev/null -w '%{http_code}\n' https://orderhub.orderapp.uk/api/health` — 200 =
   open (skip this section); 302 = gated (expected).
2. Create a service token in the Cloudflare dashboard for the orderhub app; add an Access policy
   allowing that token to reach `/api/`.
3. **`mcp_server/client.py` already sends the CF Access headers** (done in `998a3de`). Set
   `CF_ACCESS_CLIENT_ID` + `CF_ACCESS_CLIENT_SECRET` in the prod `mcp_server/.env` (+ password
   manager); the client attaches `CF-Access-Client-Id` / `CF-Access-Client-Secret` to **every**
   request (client-level defaults, so `_login` is covered too) whenever **both** are set, and
   nothing when unset (dev stays ungated). It is both-or-neither: a half-configured pair sends a
   token Cloudflare rejects with a 302 the re-auth path can't read. Leave both blank on dev.

**D. Register prod as a SEPARATE MCP server** (`orderhub-prod`, `ORDERHUB_API_URL=https://orderhub.orderapp.uk`),
not by editing the dev URL — writes are append-only with no undo, so you never want to discover
mid-session you were pointed at the wrong database.

## Revocation

`UPDATE users SET is_active = false WHERE email = 'agent@orderhub.dev';` — checked by both
`get_current_user` and `/api/auth/refresh`, so access dies within 15 min. (An `api_keys` table
with a real revocation list is filed as a precondition for any *remote* transport.)

## Deliberately NOT done (see `task.md` MCP-WAREHOUSE + the memory backlog)

- **Remote transport (Streamable HTTP).** Would let Cowork / phone / web drive it, but it's a
  separate multi-day sprint (mcp ≥1.8 + pydantic collision, nginx `proxy_buffering off`,
  `api_keys` auth, unproven prod streaming) with poor cost/benefit for single-operator warehouse
  entry from the desk. stdio + service token covers the real use case.
- **FX-CONVERSION (UAH→USD).** The sprint that makes populated warehouse data change COGS for the
  3 USD shops (today: KoraKlenu only). The next big sprint after warehouse data is in.
- Historical COGS recompute; product `cost_price` wiring (feeds nothing today).
