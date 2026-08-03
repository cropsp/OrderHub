"""OrderHub MCP server — authenticated REST client.

MCP-WAREHOUSE §5.4: tools reach OrderHub over its own REST API rather than by
importing backend services. That is the whole point of the design — every write
travels the same routers as the UI, so the shop-scope guard
(`assert_shop_access`), the capability guard (`require_capability`) and the
`test_money_field_completeness` / `test_route_scope_completeness` guards all keep
covering the agent. There is deliberately no second write path.

Auth (§5.7): log in once as the agent user, keep the httpOnly refresh cookie in
the jar, and mint a fresh 15-minute access token on 401. Revocation is
`is_active=False` on the agent user, which both `get_current_user` and
`/api/auth/refresh` check.

Cloudflare Access: prod is Access-gated, so a service token (CF-Access-Client-Id
/ -Secret) is set as DEFAULT headers on the client rather than per request. That
placement is load-bearing — Access gates the hostname, so `/api/auth/login` and
`/api/auth/refresh` need the token too, and those go through `self._http`
directly without passing through `_send`. Without the token an Access-gated host
answers 302 to a login page, which is not a 401 and would not trigger the
re-auth path. Dev is ungated and sends nothing.
"""

import asyncio
from typing import Any

import httpx

from config import Config


class OrderHubError(RuntimeError):
    """A non-2xx response from OrderHub.

    Carries the API's own `{"detail": ...}` message through to the agent
    verbatim. This matters: a 403 from the shop-scope guard must read as a
    permission error, not as a generic tool failure, or the agent will retry
    something it is never allowed to do.
    """

    def __init__(self, status_code: int, detail: str, method: str, path: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{method} {path} -> {status_code}: {detail}")


class OrderHubClient:
    """Thin authenticated wrapper over the OrderHub REST API."""

    def __init__(self, config: Config, transport: httpx.AsyncBaseTransport | None = None):
        self._config = config
        self._access_token: str | None = None
        # One lock so concurrent tool calls that all hit a 401 re-authenticate
        # once between them instead of stampeding the login endpoint.
        self._auth_lock = asyncio.Lock()
        self._http = httpx.AsyncClient(
            base_url=config.api_url,
            timeout=config.timeout_s,
            # The refresh token is an httpOnly cookie scoped to /api/auth; the
            # jar keeps it so `_reauthenticate` can mint access tokens without
            # re-sending the password.
            cookies=httpx.Cookies(),
            # Empty on dev. Client-level so login/refresh carry it too — see the
            # module docstring. httpx merges these into every request, and a
            # per-request header of the same name would win, so `_send`'s
            # Authorization header coexists with them rather than replacing them.
            headers=config.access_headers(),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── auth ───────────────────────────────────────────────

    async def _login(self) -> None:
        response = await self._http.post(
            "/api/auth/login",
            json={
                "email": self._config.agent_email,
                "password": self._config.agent_password,
            },
        )
        if response.status_code != 200:
            raise OrderHubError(
                response.status_code,
                _detail_of(response),
                "POST",
                "/api/auth/login",
            )
        self._access_token = response.json()["access_token"]

    async def _reauthenticate(self) -> None:
        """Refresh the access token, falling back to a full login.

        The refresh cookie rotates on every use and lasts 30 days, so the
        password is normally only sent once per process.
        """
        try:
            response = await self._http.post("/api/auth/refresh")
            if response.status_code == 200:
                self._access_token = response.json()["access_token"]
                return
        except httpx.HTTPError:
            pass  # fall through to a full login
        await self._login()

    # ── requests ───────────────────────────────────────────

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        """Issue an authenticated request, retrying once on 401.

        Returns the parsed JSON body, or None for 204.
        """
        if self._access_token is None:
            async with self._auth_lock:
                if self._access_token is None:
                    await self._login()

        response = await self._send(method, path, params=params, json=json)

        if response.status_code == 401:
            stale = self._access_token
            async with self._auth_lock:
                # Another coroutine may have refreshed while we waited.
                if self._access_token == stale:
                    await self._reauthenticate()
            response = await self._send(method, path, params=params, json=json)

        if response.status_code >= 400:
            raise OrderHubError(
                response.status_code, _detail_of(response), method.upper(), path
            )

        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        json: Any | None,
    ) -> httpx.Response:
        return await self._http.request(
            method,
            path,
            params=_drop_none(params),
            json=json,
            headers={"Authorization": f"Bearer {self._access_token}"},
        )

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, body: Any | None = None) -> Any:
        return await self.request("POST", path, json=body)

    async def patch(self, path: str, body: Any) -> Any:
        return await self.request("PATCH", path, json=body)

    async def put(self, path: str, body: Any) -> Any:
        return await self.request("PUT", path, json=body)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)


def _drop_none(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Omit unset query params so the API's own defaults apply."""
    if not params:
        return None
    return {k: v for k, v in params.items() if v is not None}


def _detail_of(response: httpx.Response) -> str:
    """Pull OrderHub's structured `{"detail": ...}` error out of a response."""
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    if isinstance(payload, dict) and "detail" in payload:
        detail = payload["detail"]
        # 422s from FastAPI validation carry a list of error objects.
        return detail if isinstance(detail, str) else repr(detail)
    return repr(payload)
