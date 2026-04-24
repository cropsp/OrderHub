# OrderHub CRM — Security Audit Report

> **Date**: 2026-04-24  
> **Scope**: Authentication, authorization, input validation, secrets management, MCP endpoints  
> **Method**: Static code review (read-only, no changes made)  
> **Auditor**: Claude Code (Opus 4.6)

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 3     |
| HIGH     | 7     |
| MEDIUM   | 8     |
| LOW      | 7     |
| **Total** | **25** |

---

## CRITICAL

### SEC-01: Refresh Token Secret Deterministically Derived from Access Token Secret

**File**: `backend/services/auth_service.py:27`  
**Code**: `REFRESH_SECRET_KEY = settings.SECRET_KEY + "-refresh"`

**Vulnerability**: The refresh token signing key is derived by appending `"-refresh"` to the access token key. If `SECRET_KEY` is compromised (logs, backup, config leak), an attacker immediately has both keys — the intended cryptographic isolation between access and refresh tokens is illusory.

**Impact**: Full account takeover. Attacker can forge both access tokens (15 min) and refresh tokens (30 days) for any user.

**Fix**: Use a second independent secret, e.g. `REFRESH_SECRET_KEY` as a separate env var, generated with `secrets.token_urlsafe(32)`.

---

### SEC-02: No Server-Side Refresh Token Revocation

**Files**: `backend/routers/auth.py:95-102`, `backend/services/auth_service.py:54-64`

**Vulnerability**: Refresh tokens are stateless JWTs with no server-side tracking. The `/logout` endpoint only deletes the browser cookie — the token itself remains cryptographically valid for its full 30-day lifetime. There is no token blacklist, no token-family tracking, and no revocation on:
- User logout
- Password change (no password change endpoint exists — see SEC-21)
- User deactivation (`is_active = False`)
- Role change

**Impact**: A stolen refresh token (XSS, cookie theft, network MITM on dev HTTP) grants persistent 30-day access that cannot be revoked. Deactivating a user does not terminate their sessions.

**Fix**: Implement one of: (a) server-side refresh token store with revocation (recommended), (b) token family rotation with reuse detection, or (c) short-lived refresh tokens with sliding window. At minimum, check `user.is_active` on every refresh (currently done — partial mitigation).

---

### SEC-03: Hardcoded Default Secrets in Config

**File**: `backend/config.py:28-31`

```python
SECRET_KEY: str = "change-me-generate-a-real-secret-key-min-32"
ENCRYPTION_KEY: str = Field("change-me-generate-a-real-fernet-key", ...)
```

**Vulnerability**: If the `.env` file is missing or incomplete, the application starts with publicly known, hardcoded secret keys. The default `SECRET_KEY` allows forging JWTs for any user. The default `ENCRYPTION_KEY` allows decrypting all Fernet-encrypted API tokens (Shopify, Nova Poshta) stored in the database.

**Impact**: Complete system compromise — JWT forgery, decryption of all stored API tokens, full data access.

**Fix**: Remove default values and fail-fast on startup if secrets are not configured. Add a startup validation check:
```python
SECRET_KEY: str  # No default — will raise on missing
ENCRYPTION_KEY: str  # No default — will raise on missing
```

---

## HIGH

### SEC-04: Webhook System User is Arbitrary DB User

**File**: `backend/routers/webhooks.py:67`

```python
user_result = await db.execute(select(User).limit(1))
system_user = user_result.scalar_one_or_none()
```

**Vulnerability**: The webhook handler grabs whichever user the DB returns first (non-deterministic without ORDER BY) to use as the "acting user" for audit trails. If no users exist, `system_user` is `None`, causing a crash in `create_order()` when it accesses `user.id` for `OrderStatusHistory.changed_by_id`.

**Impact**: Inaccurate audit trails (wrong user attributed to webhook-created orders). NullReferenceError crash on empty-user databases.

**Fix**: Create a dedicated system user during migration (not seed), or allow `create_order` to accept `system_user_id: UUID | None` and handle the null case in history creation.

---

### SEC-05: No Multi-Tenant Shop Isolation

**File**: `backend/routers/dependencies.py:64-89`

```python
# TODO: Implement strict multi-tenant ownership check if needed.
```

**Vulnerability**: `get_shop_for_user()` verifies the shop exists but does not check ownership. Any authenticated user (including designers) can access any shop's data, products, and orders by providing a valid `shop_id`. The products and packaging routers use `get_shop_for_user` via `require_platform`, inheriting this gap.

**Impact**: Cross-tenant data exposure. A designer from Shop A can view Shop B's products, orders, and customer data.

**Fix**: Add `shop.owner_id` field or a `UserShopAccess` junction table, and enforce the check in `get_shop_for_user()`.

---

### SEC-06: MCP Single Global SSE Transport Race Condition

**File**: `backend/routers/mcp.py:31, 106-107`

```python
sse_transport: SseServerTransport | None = None
# ...
sse_transport = transport  # Overwrites previous connection
```

**Vulnerability**: A single global variable holds the SSE transport. A second agent connection overwrites the first's transport reference. Messages from the first agent could be routed to the second agent's context, and the first agent's session silently breaks.

**Impact**: Data leakage between AI agent sessions. Denial of service for the first connected agent.

**Fix**: Use a session-keyed dictionary (e.g., `Dict[str, SseServerTransport]`) with session IDs, or use the MCP SDK's built-in session management.

---

### SEC-07: Internal Error Details Leaked to Clients

**Files**: `backend/routers/shipping.py:60,84,152,190,253`, `backend/routers/imports.py:49`, `backend/routers/shops.py:199`

```python
raise HTTPException(status_code=400, detail=str(e))
```

**Vulnerability**: Multiple endpoints pass raw exception messages directly to clients via `detail=str(e)`. These can expose internal paths, database errors, Nova Poshta API error codes, Python tracebacks, and potentially encrypted token values in error context.

**Impact**: Information disclosure that aids further attacks (database type, internal architecture, third-party API details).

**Fix**: Log the full exception server-side, return generic user-facing messages:
```python
logger.error(f"NP API Error: {e}", exc_info=True)
raise HTTPException(status_code=400, detail="Failed to communicate with shipping provider")
```

---

### SEC-08: No File Upload Restrictions

**File**: `backend/routers/attachments.py:22-64`

**Vulnerability**: The attachment upload endpoint has:
- No file size limit (can upload multi-GB files)
- No file type whitelist (executables, scripts, HTML files accepted)
- No content-type validation (MIME type is taken from client headers, not verified)
- No total storage quota per order or user

**Impact**: Disk exhaustion DoS. Stored XSS if HTML/SVG files are served inline. Potential malware storage.

**Fix**: Add `max_size` validation (e.g., 10MB), whitelist allowed MIME types (images, PDFs), validate content headers match actual file content, and set `Content-Disposition: attachment` on download responses.

---

### SEC-09: Product/Packaging Routes Missing RBAC

**Files**:
- `backend/routers/products.py:66-89` — `PATCH /products/{id}`, `DELETE /products/{id}`
- `backend/routers/packaging.py:42-65` — `PATCH /packaging-boxes/{id}`, `DELETE /packaging-boxes/{id}`

**Vulnerability**: These endpoints only require `get_current_user` (any authenticated user). Designers can modify or delete products and packaging boxes, which should be restricted to owner/manager roles. Compare with the list/create endpoints on these same routers, which enforce `require_platform` (which chains through `get_shop_for_user`).

**Impact**: Unauthorized data modification. A designer could delete all product catalog entries.

**Fix**: Add `require_role(UserRole.OWNER, UserRole.MANAGER)` to these endpoints, or at minimum chain through `get_shop_for_user` to enforce shop-level access.

---

### SEC-10: Attachment Download Bypasses Order Access Control

**File**: `backend/routers/attachments.py:92-113`

**Vulnerability**: `GET /api/attachments/{attachment_id}` checks only that the attachment exists. It does not verify whether the requesting user has access to the parent order. A designer can download attachments from any order (including orders they aren't assigned to) by knowing or guessing the attachment UUID.

**Impact**: Unauthorized access to order files (mockups, reference images, customer documents).

**Fix**: Join to the Order table and apply the same designer-assignment check used in `list_attachments_by_order`.

---

## MEDIUM

### SEC-11: Deprecated JWT Library (python-jose)

**File**: `backend/services/auth_service.py:4` (`from jose import JWTError, jwt`)

**Vulnerability**: `python-jose` is [no longer maintained](https://github.com/mpdavis/python-jose/issues/310) and has known issues. The project has no security patch pipeline. Community has moved to `PyJWT` or `joserfc`.

**Impact**: Supply chain risk — future JWT vulnerabilities will not be patched.

**Fix**: Migrate to `PyJWT` (drop-in replacement for basic HS256 usage) or `joserfc`.

---

### SEC-12: Import Preview Token Not Bound to User

**File**: `backend/services/import_service.py:15-49`

**Vulnerability**: CSV import previews are stored in process memory (`_storage` class dict). The preview token is a plain UUID with no cryptographic binding to the requesting user or session. Any authenticated user who obtains a valid token could confirm another user's import. In multi-worker deployments (gunicorn with multiple workers), preview and confirm may hit different workers, causing silent failures.

**Impact**: Unauthorized import execution. Silent data loss in scaled deployments.

**Fix**: Bind the token to `user_id` and validate on confirm. For multi-worker: use Redis or DB-backed storage.

---

### SEC-13: Seed Script Has No Production Guard

**File**: `backend/seed.py:46-66`

**Vulnerability**: Hardcoded credentials (`owner123`, `manager123`, `designer123`) with no check for `ENVIRONMENT != production`. The `--if-empty` flag only checks for existing users, not the environment. If run in production on a fresh database, trivially guessable accounts are created.

**Impact**: Unauthorized access via known default credentials.

**Fix**: Add `if settings.ENVIRONMENT == "production": sys.exit("Seed blocked in production")` at the top of `main()`.

---

### SEC-14: Scheduler Creates Non-Persistent Fake User

**File**: `backend/scheduler.py:23-28`

```python
system_user = User(
    id="00000000-0000-0000-0000-000000000000",
    email="system@orderhub.dev",
    role=UserRole.OWNER,
    ...
)
```

**Vulnerability**: The scheduler creates an in-memory User object with a hardcoded UUID that does not exist in the database. The `OrderStatusHistory.changed_by_id` foreign key references this non-existent UUID, violating referential integrity (or silently storing a dangling reference if FK is not enforced). Any code that later joins on `changed_by` will return NULL for these records.

**Impact**: Corrupted audit trail. Potential FK constraint violations.

**Fix**: Create a persistent system user via Alembic data migration with a well-known UUID, or use the same approach as webhooks (with the fix from SEC-04).

---

### SEC-15: No Rate Limiting

**File**: `backend/main.py` (absent)

**Vulnerability**: No rate limiting middleware on any endpoint. Attack surfaces:
- `/api/auth/login` — brute-force password attacks
- `/api/shipping/cities`, `/api/shipping/warehouses` — exhaust Nova Poshta API quotas
- `/api/imports/etsy` — repeated large CSV uploads for DoS
- `/api/orders/action/export` — repeated CSV exports loading 10k orders into memory

**Impact**: Account compromise via brute force. Third-party API quota exhaustion. Memory exhaustion DoS.

**Fix**: Add `slowapi` or a custom middleware with per-IP/per-user rate limits. At minimum, rate-limit `/api/auth/login` to ~5 attempts per minute.

---

### SEC-16: PII Logged in Plaintext

**File**: `backend/routers/shipping.py:235`

```python
logger.info(f"Creating NP TTN with payload: {payload}")
```

**Vulnerability**: The full Nova Poshta TTN payload is logged, including customer names, phone numbers, physical addresses, and sender details. Log files rotate at 5MB × 5 backups = 25MB of PII on disk.

**Impact**: GDPR/privacy violation. PII exposure if logs are collected by a monitoring system or leaked.

**Fix**: Log only non-PII fields (order ID, shop ID, status) or redact sensitive fields before logging.

---

### SEC-17: CORS Allows All Methods and Headers

**File**: `backend/main.py:47-53`

```python
allow_methods=["*"],
allow_headers=["*"],
```

**Vulnerability**: While the origin is properly restricted to `FRONTEND_URL`, allowing all methods and headers is unnecessarily permissive. This allows TRACE, PUT, DELETE, and custom headers at the CORS level.

**Impact**: Increased attack surface. TRACE method can be used for cross-site tracing attacks in some configurations.

**Fix**: Restrict to actually used methods and headers:
```python
allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
allow_headers=["Authorization", "Content-Type"],
```

---

### SEC-18: CreateTTNRequest Schema Missing Fields Referenced in Code

**File**: `backend/routers/shipping.py:30-35` vs lines `107, 196-200`

**Vulnerability**: The `CreateTTNRequest` Pydantic schema defines only `weight`, `description`, `volume`, `cash_on_delivery`, `cod_amount`. But the handler accesses `body.parcel_override` (line 107) and `body.length`, `body.width`, `body.height` (lines 197-198) which don't exist on the schema. Accessing these will raise `AttributeError` at runtime.

**Impact**: Runtime crash on TTN creation when those code paths execute. The unhandled `AttributeError` could leak internal details via the 500 error handler.

**Fix**: Either add the missing fields to `CreateTTNRequest`, or remove the dead code paths that reference them.

---

## LOW

### SEC-19: SQL Echo Enabled in Development

**File**: `backend/database.py:21`

```python
echo=settings.is_development,
```

**Vulnerability**: All SQL queries are logged to stdout in development mode. Queries may contain user emails, hashed passwords (in INSERT statements), and customer PII.

**Impact**: PII exposure in development logs/terminals.

**Fix**: Set `echo=False` by default, or use `echo="debug"` which only logs at DEBUG level.

---

### SEC-20: Default DB Credentials in Config and .env.example

**Files**: `backend/config.py:23-25`, `.env.example:2-4`

```python
POSTGRES_USER: str = "crm"
POSTGRES_PASSWORD: str = "crm_pass"
```

**Vulnerability**: Default database credentials are hardcoded in config defaults and `.env.example`. Copy-pasting to production without changing results in well-known DB credentials.

**Impact**: Database compromise if PostgreSQL is network-accessible.

**Fix**: Remove defaults for DB credentials (fail-fast) or add prominent warnings in `.env.example`.

---

### SEC-21: No Password Change Endpoint

**Files**: `backend/routers/users.py`, `backend/routers/auth.py`

**Vulnerability**: There is no endpoint for users to change their own password. Temporary passwords generated during user creation (`generate_temp_password()`) are permanent. The only way to change a password is direct DB modification.

**Impact**: Users cannot rotate compromised credentials. Temporary passwords become permanent secrets.

**Fix**: Add `POST /api/auth/change-password` requiring the current password and setting a new one.

---

### SEC-22: ILIKE Wildcard Injection in Search

**Files**: `backend/routers/customers.py:43-44`, `backend/services/order_service.py:54`

```python
term = f"%{search}%"
conditions.append(Customer.email.ilike(term))
```

**Vulnerability**: Special characters `%` and `_` in user-supplied search terms are not escaped. A search for `%` returns all records. A search for `a]%` could be used to probe data patterns. While SQLAlchemy properly parameterizes the value (no SQL injection), the wildcard behavior allows data enumeration.

**Impact**: Minor information disclosure via pattern probing.

**Fix**: Escape `%` and `_` in search input before building the ILIKE term:
```python
escaped = search.replace("%", "\\%").replace("_", "\\_")
term = f"%{escaped}%"
```

---

### SEC-23: Path Traversal Check Off-by-One

**File**: `backend/services/file_storage.py:50`

```python
if uploads_dir not in abs_path.parents:
    return None
```

**Vulnerability**: The check `uploads_dir not in abs_path.parents` fails when `abs_path` is a file directly inside `UPLOADS_DIR` (not in a subdirectory), because `abs_path.parents` does not include `abs_path` itself. In practice, the upload logic always creates `order_id/` subdirectories, so this is unlikely to be exploited with current code.

**Impact**: Theoretical path traversal on edge-case file locations. Low practical risk due to upload path structure.

**Fix**: Use `abs_path.is_relative_to(uploads_dir)` (Python 3.9+) for a correct check.

---

### SEC-24: OpenAPI Docs Gated Only by Environment Flag

**File**: `backend/main.py:43-44`

```python
docs_url="/docs" if settings.is_development else None,
redoc_url="/redoc" if settings.is_development else None,
```

**Vulnerability**: API documentation is exposed when `ENVIRONMENT=development`. If this flag is not updated for production deployment, the full API schema is accessible without authentication, revealing all endpoints, parameters, and response models.

**Impact**: Information disclosure (full API contract visible to attackers).

**Fix**: This is acceptable if the deployment checklist enforces `ENVIRONMENT=production`. Consider adding auth to the docs endpoint as defense-in-depth.

---

### SEC-25: Shopify Retry Catches All Exceptions

**File**: `backend/services/shopify_sync.py:67`

```python
retry=retry_if_exception_type((httpx.HTTPError, Exception)),
```

**Vulnerability**: Retrying on `Exception` means authentication failures (401), permission errors (403), and data parsing errors are retried 3 times with exponential backoff. This wastes time and could trigger Shopify's rate limits.

**Impact**: Unnecessary API calls. Potential rate-limit lockout from Shopify.

**Fix**: Retry only on transient errors:
```python
retry=retry_if_exception_type(httpx.HTTPError),
```

---

## Appendix: Positive Findings

The audit also identified several well-implemented security patterns:

1. **JWT structure**: Separate `type` claims for access/refresh tokens, preventing token confusion attacks (`auth_service.py:49,62`).
2. **Refresh cookie settings**: `httpOnly=True`, `samesite="strict"`, `secure` in production, scoped `path="/api/auth"` (`auth.py:42-49`).
3. **Bcrypt hashing**: Proper use of `passlib` with auto-deprecation (`auth_service.py:24`).
4. **Fernet encryption**: API tokens encrypted at rest with proper key management pattern (`encryption_service.py`).
5. **Webhook HMAC verification**: Shopify webhooks verified with `hmac.compare_digest()` (constant-time comparison) (`webhooks.py:29-32`).
6. **File upload path traversal protection**: UUID-prefixed filenames and `resolve()` check in `get_absolute_path()` (`file_storage.py:26-27,43-57`).
7. **RBAC on sensitive routes**: Owner-only guards on user management, shop CRUD, financial fields (`users.py`, `shops.py`, `order_service.py:258`).
8. **Designer data scoping**: Designers see only assigned orders in list and detail views (`orders.py:57-58,94-95`).
9. **Token rotation on refresh**: New refresh token issued on each refresh call, limiting window for stolen tokens (`auth.py:80-90`).
10. **CORS origin restriction**: Only `FRONTEND_URL` origin allowed, not wildcard (`main.py:49`).
