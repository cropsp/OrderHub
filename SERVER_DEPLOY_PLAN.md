# OrderHub — LAN Deployment Plan (Step 4)

**Target:** `prorder@192.168.31.71` (`ssh orderhub`), Ubuntu 26.04 LTS, hardened
(ufw allows only 22/tcp from `192.168.31.0/24`), Docker 29.6.1 + Compose v2.3.1
already installed. 98G disk, 86G free.

**Goal:** "Get OrderHub running on the LAN first, harden later." idlaser is
**deferred** — backend must build and run without it. Remote access (Cloudflare
Tunnel + Access) was a later phase — now **DONE**, see §10. The app is reachable at
`https://orderhub.orderapp.uk` and the LAN `:80` publish has been removed.

**Scope guardrails applied now (cheap safety):** `ENVIRONMENT=production`, real
generated secrets, Postgres bound to `127.0.0.1`, backend not published to the LAN,
no source bind-mounts on the server, `restart: unless-stopped`.

---

## 1. Getting the code onto the server → **git clone (no submodule)** + scp overlay

**Facts established (read-only):**
- `origin` = `https://github.com/cropsp/OrderHub` → **public** (unauth HTTP 200).
- `github.com/cropsp/idlaser` → **private** (unauth 404).
- Server has **no GitHub auth** (`gh` not installed, `~/.ssh` holds only the login key),
  and no outbound GitHub credentials.

**Decision: `git clone` the public OrderHub repo on the server (WITHOUT
`--recurse-submodules`), then `scp` the 3 non-repo files.**

Justification: OrderHub is public, so `git clone` needs **zero** GitHub credentials on
the server. It gives a reproducible tree from canonical `main` (no local WSL drift —
our working copy has uncommitted `start-dev.sh`/`.env.bak` noise) and trivial `git pull`
updates later. `--recurse-submodules` is deliberately omitted because idlaser is private
and would 404; the empty `backend/external/idlaser` gitlink dir is harmless (the deploy
Dockerfile below never touches it). rsync's only real advantage — not needing server-side
GitHub auth — is moot because the repo is public.

Three files are NOT in the repo (either intentionally uncommitted or secret) and travel
by `scp` from the local WSL working copy after cloning:
- `backend/Dockerfile.deploy` (new, see §2)
- `docker-compose.prod.yml` (new, see §4)
- `.env` (secret, see §3)

> Alternative considered — rsync the whole local working copy: rejected as primary
> because it ships local drift + the populated private idlaser submodule (which we want
> deferred), and offers no auth advantage here.

Server layout: `/home/prorder/OrderHub` (project name → compose prefix `orderhub`).

---

## 2. idlaser deferral → new `backend/Dockerfile.deploy` (no edits to existing files)

**How idlaser is wired today (verified):**
- `services/idlaser_service.py:50` — `from idlaser.api import (...)` wrapped in
  `try/except ImportError`; on failure the symbols become `None`.
- `main.py:39` — lifespan `from idlaser.api import set_model_path` wrapped in
  `try/except ImportError`; logs a warning and continues.
- `routers/idlaser.py`, `models/idlaser_draft_job.py`, `schemas/idlaser_draft_job.py`
  are pure Python (no idlaser import at module load) → the app imports and starts fine.
- All runtime deps the service needs at import time (`tenacity`, `aiofiles`,
  `sse-starlette`) are already in `backend/requirements.txt`. onnxruntime is also
  guarded (`try/except`).
- **The ONLY hard dependency is the image build:** `backend/Dockerfile:20-21`
  `COPY ./external/idlaser` + `RUN pip install -e ./external/idlaser`. Without the
  populated submodule this step fails the build.

**Minimal, reversible change:** add `backend/Dockerfile.deploy` = a copy of
`backend/Dockerfile` with **lines 20–21 (the two idlaser lines) removed**. Everything
else identical. The prod compose points the backend build at this dockerfile. Reverting
= delete the file. No existing tracked file is edited.

```dockerfile
# backend/Dockerfile.deploy — idlaser-less build for LAN deploy (idlaser deferred)
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# (idlaser COPY + editable install intentionally omitted — deferred)
COPY . .
RUN mkdir -p /app/uploads
EXPOSE 8000
CMD ["bash", "entrypoint.sh"]
```

**What stops working without idlaser (and ONLY this):** the **"Generate Draft"** feature
on the order Attachments panel — all three routes under `routers/idlaser.py`
(`generate-draft`, `manual-corners`, `status`). The button still renders but the pipeline
returns unavailable (service symbols are `None`). Everything else — orders, shops,
Shopify/Etsy import, Nova Poshta, dashboard, products, attachments, users/auth — is
unaffected. Lifespan logs one warning: `idlaser package not installed`.

---

## 3. `.env` — required variables (DO NOT generate yet; plan only)

Single `/home/prorder/OrderHub/.env`, `chmod 600`, never committed. Based on
`config.py` (`Settings`) and `.env.example`.

**Generate on the server (strong, random):**
| Var | How | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -base64 24` | must match the password inside `DATABASE_URL` |
| `SECRET_KEY` | `python -c "import secrets;print(secrets.token_urlsafe(32))"` | prod boot **fails** if left as `change-me…` (SEC-03 guard in `config.py`) |
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` | **⚠ IRREPLACEABLE** — encrypts all Nova Poshta API keys in the DB (Fernet). Lose/rotate it → every stored NP key is undecryptable. **Back this up the moment it's created.** Aliased as `FERNET_KEY`. |
| `REFRESH_SECRET_KEY` | same as SECRET_KEY cmd | Generate now. Setting/rotating it later logs out every user. |

**Fixed / derived (no input needed):**
| Var | Value |
|---|---|
| `POSTGRES_USER` | `crm` |
| `POSTGRES_DB` | `crm_db` |
| `DATABASE_URL` | `postgresql+asyncpg://crm:<POSTGRES_PASSWORD>@postgres:5432/crm_db` |
| `ENVIRONMENT` | `production`  ← critical: enables secret validation; our prod command also skips the dev seed |
| `FRONTEND_URL` | `http://192.168.31.71` (matches published frontend port 80 — see §5) |
| `UPLOADS_DIR` | `/app/uploads` |
| `BASE_CURRENCY` | `USD` |
| `IDLASER_*` | **leave unset** — defaults point at `/app/external/idlaser/*` which won't exist; lifespan warns, non-fatal. Do NOT set the obsolete `/idlaser/*` paths. |

**Need your input (email features — see Open Questions):**
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_NAME`.
Without valid SMTP, the app **still boots**; only outbound email (password-reset / temp
password delivery for new users, notifications) fails. For "up first" we can ship blank
SMTP and fill later — but note new-user temp passwords are emailed, so the owner bootstrap
in §7 deliberately sets a known password directly instead of relying on email.

---

## 4. Compose for LAN bring-up → **new standalone `docker-compose.prod.yml`**

Do **not** reuse `docker-compose.dev.yml` (source bind-mounts + `--dev` seed + `--reload`).
Do **not** use `docker-compose.yml` as-is (it publishes `postgres 5432:5432` and
`backend 8000:8000` to all interfaces, and its `entrypoint.sh` hard-codes `--reload`).

Use a **standalone** prod file rather than a base+override: Compose **appends** `ports`
lists on merge, so an override cannot *remove* the base file's `8000`/`5432` publishes.
A standalone file gives exact control and reverts by deletion.

```yaml
# docker-compose.prod.yml — LAN bring-up (idlaser deferred)
services:
  postgres:
    image: postgres:16-alpine
    env_file: .env
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"          # host-local only (psql/backup) — NOT the LAN
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.deploy      # idlaser-less build (§2)
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - uploads_data:/app/uploads        # named volume only — NO source bind-mount
    # No published ports — reached only via the frontend nginx proxy on the internal net.
    # Override the entrypoint to run migrations then uvicorn WITHOUT --reload and
    # WITHOUT the dev seed (entrypoint.sh hard-codes --reload; we bypass it here).
    command: ["bash", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port 8000"]
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile             # prod nginx image
    depends_on:
      - backend
    ports:
      - "80:80"                          # LAN entry point → http://192.168.31.71
    restart: unless-stopped

volumes:
  postgres_data:
  uploads_data:
```

Notes: frontend `nginx.conf` proxies `/api/` → `http://backend:8000` on the compose
network, and `frontend/src/api/client.ts` uses a **relative** `/api` base, so the browser
talks same-origin to `:80` and the backend needs no LAN port. The `command:` override is
what fixes the `--reload`/seed issue minimally without editing the shared `entrypoint.sh`.

---

## 5. LAN ports (Docker bypasses ufw — publish only what's intended)

Docker inserts its own iptables rules **ahead** of ufw, so any *published* port is LAN-
reachable regardless of the `deny (incoming)` policy. Therefore publish deliberately:

| Service | Publish | Reachable from | Rationale |
|---|---|---|---|
| frontend | ~~`80:80`~~ **removed (§10)** | tunnel only (`http://frontend:80` internal) | LAN publish dropped once the tunnel was verified — see §10 |
| backend | *(none)* | internal compose net only | API + DB creds stay off the LAN; nginx proxies it |
| postgres | `127.0.0.1:5432:5432` | server localhost only | psql/backup convenience; the `127.0.0.1` bind keeps Docker from exposing it to the LAN |

No ufw changes needed or made. **Update (§10):** the frontend `80:80` publish has since been
removed — the app is now reachable **only** through the Cloudflare Tunnel. Nothing is published
to the LAN anymore (postgres stays `127.0.0.1`-only). ufw remains SSH-only.

---

## 6. Migrations — run automatically on backend start

The backend `command` runs `alembic upgrade head` before uvicorn. There are **16**
migrations in `backend/alembic/versions/`. `depends_on: postgres healthy` guarantees the
DB is accepting connections first. First-run applies the full chain on an empty DB,
including the `ShopSource.MANUAL` enum and the persistent system user
(`a1b2c3d4e5f6_add_persistent_system_user`, UUID `…0001`).

First-run risks (all low, single-node): (a) migrations are linear and already exercised in
dev — no branch/merge heads expected; verify with `alembic heads` showing a single head.
(b) Only one backend replica runs, so no concurrent-migration race. (c) If a migration
fails mid-way the container exits non-zero (visible in logs) and `restart: unless-stopped`
will retry — inspect logs before assuming a transient failure.

---

## 7. First owner account bootstrap (dev seed is skipped in prod)

`routers/users.py:52` `create_user` is `require_role(UserRole.OWNER)` and there is **no
self-registration** → chicken-and-egg. The dev seed (`seed.py`) is intentionally NOT run
(prod command omits `--dev`), and it would also insert dummy shops/orders we don't want.

Bootstrap one owner via a one-off exec that **reuses existing code**
(`services/auth_service.hash_password`, `models.User`, `database.async_session_factory`):

```bash
docker compose -f docker-compose.prod.yml exec backend python - <<'PY'
import asyncio, uuid
from database import async_session_factory
from models import User, UserRole
from services.auth_service import hash_password
async def main():
    async with async_session_factory() as s:
        s.add(User(id=uuid.uuid4(), email="OWNER_EMAIL", full_name="OWNER NAME",
                    role=UserRole.OWNER, hashed_password=hash_password("STRONG_TEMP_PW"),
                    is_active=True))
        await s.commit()
    print("owner created")
asyncio.run(main())
PY
```

Then log in at `http://192.168.31.71` with those credentials and create the manager/
designer users through the UI (that path emails temp passwords once SMTP is set, or the
owner can reset). Change the owner password after first login.

---

## 8. Data persistence & backup (later)

Two named volumes hold all state (compose prefix `orderhub`):
- `orderhub_postgres_data` — the entire database (orders, users, encrypted NP keys, audit).
- `orderhub_uploads_data` — `/app/uploads`: customer reference photos, attachments, any
  generated artifacts.

**Must be backed up later** (flagged for the hardening phase, not built now):
1. `orderhub_postgres_data` — via `pg_dump` (`docker compose exec postgres pg_dump …`) or
   a volume tar.
2. `orderhub_uploads_data` — volume tar.
3. **`.env`, specifically `ENCRYPTION_KEY`** — irreplaceable; a DB backup is useless for
   the encrypted NP keys without it. Store it separately from the DB dump.

Docker's default local volumes persist across `docker compose down`/reboots; only
`down -v` destroys them.

---

## 9. Execution checklist (small, verifiable steps + rollback)

Run from local WSL unless noted. `⚠` = risky step.

1. **Create the 2 deploy files locally** — `backend/Dockerfile.deploy` (§2),
   `docker-compose.prod.yml` (§4).
   *Verify:* `docker compose -f docker-compose.prod.yml config -q` parses clean.
   *Rollback:* delete the files.

2. **Clone on server (no submodules).**
   `ssh orderhub 'git clone https://github.com/cropsp/OrderHub ~/OrderHub'`
   *Verify:* `ssh orderhub 'ls ~/OrderHub/backend/entrypoint.sh ~/OrderHub/frontend/nginx.conf'`.
   *Rollback:* `rm -rf ~/OrderHub`.

3. **scp the overlay files** to the clone: `Dockerfile.deploy` →
   `~/OrderHub/backend/`, `docker-compose.prod.yml` → `~/OrderHub/`.
   *Verify:* both present on server.
   *Rollback:* delete them on the server.

4. **⚠ Build `.env` on the server** (§3): generate the 4 secrets, fill fixed vars, leave
   SMTP blank-or-provided, `chmod 600 .env`. **Immediately copy `ENCRYPTION_KEY` to a safe
   place off the box.**
   *Verify:* `grep -c '^' .env` has all required keys; no `change-me` left in
   `SECRET_KEY`/`ENCRYPTION_KEY`.
   *Rollback:* `rm .env` (but the generated `ENCRYPTION_KEY` is only safe to discard
   *before* any NP key is stored — after that it's irreplaceable).

5. **⚠ Build images.**
   `ssh orderhub 'cd ~/OrderHub && docker compose -f docker-compose.prod.yml build'`
   *Verify:* backend + frontend images build; no idlaser COPY error.
   *Rollback:* `docker compose -f docker-compose.prod.yml down --rmi local`.

6. **⚠ Bring up postgres first, confirm healthy.**
   `docker compose -f docker-compose.prod.yml up -d postgres` → wait →
   `docker compose -f docker-compose.prod.yml ps` shows `healthy`.
   *Rollback:* `down` (no `-v` — keep the fresh volume) / `down -v` to wipe.

7. **⚠ Start backend; migrations run.**
   `docker compose -f docker-compose.prod.yml up -d backend` then
   `docker compose -f docker-compose.prod.yml logs -f backend`.
   *Verify:* logs show `alembic upgrade head` completing, `Application startup complete`,
   one benign `idlaser package not installed` warning, and no secret-placeholder crash.
   *Rollback:* `down` backend; fix `.env`/migration; the volume can be wiped with `down -v`
   while the DB is still empty.

8. **Start frontend.**
   `docker compose -f docker-compose.prod.yml up -d frontend`.
   *Verify:* from a LAN machine, `http://192.168.31.71` loads the login page;
   `curl -s http://192.168.31.71/api/... ` reaches the backend through nginx.
   *Rollback:* `down` frontend.

9. **Bootstrap owner** (§7), log in, smoke-test: create a shop, a manual order, open the
   dashboard.
   *Rollback:* delete the user row / `down -v` to start clean.

10. **Confirm persistence:** `docker compose -f docker-compose.prod.yml restart` and
    re-login to confirm data survives.

---

## 10. Remote access — Cloudflare Tunnel + Access (DONE, 2026-07-10)

The app is now served publicly at **`https://orderhub.orderapp.uk`** through a Cloudflare
Tunnel, with **zero inbound ports** on the server. ufw stays SSH-only; the frontend `80:80`
LAN publish (§5) has been removed. Delivered in three steps, each reversible.

### 10.1 `cloudflared` connector → new service in `docker-compose.prod.yml`

A remotely-managed (token) tunnel: routing/public-hostname config lives in the Cloudflare
dashboard, **not** on the server. The connector only needs its token and outbound egress.

```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel --no-autoupdate run
    environment:
      TUNNEL_TOKEN: ${TUNNEL_TOKEN}      # connector token from .env (git-ignored)
    # No published ports — outbound-only connector. Joins orderhub_default and can
    # reach http://frontend:80. Public hostname/ingress is managed in the Cloudflare
    # dashboard (remotely-managed tunnel), not configured locally here.
    restart: unless-stopped
```

- **No `ports:`** — outbound-only. Joins the default compose network (`orderhub_default`),
  same as `frontend`, so it reaches the app at **`http://frontend:80`** (nginx serves the
  SPA and proxies `/api/` → `backend:8000`). The dashboard hostname route points here.
- **Token** stored as `TUNNEL_TOKEN=…` in `/home/prorder/OrderHub/.env` (`chmod 600`,
  git-ignored — never committed). Extracted from the `docker run … --token <TOKEN>` command
  Cloudflare generated. Tunnel ID `3efa1e07-137c-47fa-b76c-82aa3b5fa58c`.
- Bring-up: `docker compose -f docker-compose.prod.yml up -d cloudflared`. The distroless
  image has **no shell/`wget`/`curl`** — verify reachability from a peer container, not from
  inside cloudflared.
- **Verified:** logs show 4 `Registered tunnel connection` lines (HA, QUIC, to `waw02`/`kbp02`
  edges); `docker compose ps cloudflared` = Up.

### 10.2 Backend origin config for the public hostname (`.env`)

- **`FRONTEND_URL=https://orderhub.orderapp.uk`** (was `http://192.168.31.71`). This is the
  app's **sole CORS allow-origin** — `main.py:71` `allow_origins=[settings.FRONTEND_URL]`.
- **No other Host/trusted-host allowlist exists** — verified there is no `TrustedHostMiddleware`,
  `ALLOWED_HOSTS`, or CSRF trusted-origins list anywhere in `backend/`, so nothing else needed
  editing. The refresh-token cookie (`routers/auth.py`) is host-only (no pinned `domain=`),
  `path=/api/auth`, `samesite=strict` — correct for a same-origin HTTPS tunnel.
- Apply: `docker compose -f docker-compose.prod.yml up -d backend` (recreate to reload env,
  **no rebuild**). Postgres recreates as a side-effect (shares `env_file: .env`); data persists
  on the named volume.
- **Verified:** `printenv FRONTEND_URL` in-container = the public URL; CORS preflight with
  `Origin: https://orderhub.orderapp.uk` echoes `access-control-allow-origin: https://orderhub.orderapp.uk`.
- **⚠ Secure-cookie consequence:** with `ENVIRONMENT=production`, the refresh cookie is set
  `secure=not is_development` → **`secure=True`**. Login/refresh therefore work over the HTTPS
  hostname but **not** over plain `http://192.168.31.71` (browsers withhold secure cookies on
  HTTP). Expected — use the HTTPS hostname. This is one more reason the LAN `:80` path is retired.

### 10.3 Take the app off the LAN — remove the frontend `80:80` publish

- Deleted the frontend service's `ports:` block entirely. **Network membership unchanged**
  (still `orderhub_default`), so cloudflared still reaches `http://frontend:80` internally.
- Apply: `docker compose -f docker-compose.prod.yml up -d frontend` (recreate only, no rebuild).
- **Verified:** `ss -tlnp | grep ':80 '` empty; `curl http://192.168.31.71/` → refused
  (exit 7 / HTTP 000); frontend Up with `80/tcp` container-internal only; internal
  `http://frontend:80/` fetch from a same-network peer → HTTP 200 serving the app HTML.

### Rollback / ops notes

- **Backups on server** (pre-change copies): `.env.bak.pre-tunnel`, `.env.bak.pre-origin`,
  `docker-compose.prod.yml.bak.pre-tunnel`, `docker-compose.prod.yml.bak.pre-lanoff`.
- **Re-expose on LAN** (debug): re-add `ports: ["80:80"]` to frontend + `up -d frontend`.
- **Rotate the tunnel token:** replace `TUNNEL_TOKEN` in `.env`, `up -d cloudflared`.
- **Public routing** (hostname → `http://frontend:80`) and **Cloudflare Access** policy are
  managed in the Cloudflare dashboard, not in this repo. No local ingress file.

---

## Decisions (confirmed) + remaining open questions

**Confirmed:**
- **Frontend port = 80** → `http://192.168.31.71` for the initial LAN bring-up.
  **Superseded (§10):** LAN publish removed; app now served via Cloudflare Tunnel at
  `https://orderhub.orderapp.uk` with `FRONTEND_URL=https://orderhub.orderapp.uk`.
- **SMTP = disabled** for this bring-up (blank SMTP vars). App boots; new-user temp-password
  emails + notifications are unavailable until added later. Owner bootstrap (§7) is
  unaffected (it sets a known password directly).
- **Checkout = `main` HEAD.**
- **DB name/user = defaults** `crm` / `crm_db`.

**Still needed before execution:**
1. **Owner account (§7):** email + display name + initial password for the first OWNER.
