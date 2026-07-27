"""OrderHub MCP client — auth lifecycle and error passthrough.

Uses httpx.MockTransport rather than a live backend: the contract under test is
this client's behaviour (bearer attachment, 401 retry, single re-auth under
concurrency, error mapping), not OrderHub's routing.
"""

import asyncio
import json

import httpx
import pytest

from client import OrderHubClient, OrderHubError, _detail_of, _drop_none
from config import Config


def _config(**over):
    base = dict(
        api_url="http://testserver",
        agent_email="agent@orderhub.dev",
        agent_password="s3cret",
        timeout_s=5.0,
    )
    base.update(over)
    return Config(**base)


class Recorder:
    """Scripted MockTransport handler that records every request it sees."""

    def __init__(self, handler):
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]

    def auth_headers(self) -> list[str | None]:
        return [r.headers.get("authorization") for r in self.requests]


def _client(handler) -> tuple[OrderHubClient, Recorder]:
    recorder = Recorder(handler)
    return (
        OrderHubClient(_config(), transport=httpx.MockTransport(recorder)),
        recorder,
    )


def _ok(payload, status=200):
    return httpx.Response(status, json=payload)


# ── login ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logs_in_once_then_attaches_bearer():
    def handler(request):
        if request.url.path == "/api/auth/login":
            return _ok({"access_token": "tok-1"})
        return _ok([{"id": "m1"}])

    client, rec = _client(handler)
    await client.get("/api/materials")
    await client.get("/api/materials")
    await client.aclose()

    assert rec.paths().count("/api/auth/login") == 1
    assert rec.auth_headers()[1:] == ["Bearer tok-1", "Bearer tok-1"]


@pytest.mark.asyncio
async def test_login_sends_configured_credentials():
    def handler(request):
        if request.url.path == "/api/auth/login":
            body = json.loads(request.content)
            assert body == {"email": "agent@orderhub.dev", "password": "s3cret"}
            return _ok({"access_token": "tok-1"})
        return _ok({})

    client, _ = _client(handler)
    await client.get("/api/shops")
    await client.aclose()


@pytest.mark.asyncio
async def test_failed_login_raises_with_detail():
    def handler(request):
        return _ok({"detail": "Invalid email or password"}, status=401)

    client, _ = _client(handler)
    with pytest.raises(OrderHubError) as exc:
        await client.get("/api/materials")
    await client.aclose()
    assert exc.value.status_code == 401
    assert "Invalid email or password" in exc.value.detail


# ── 401 retry ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_expired_token_refreshes_and_retries():
    state = {"expired": True}

    def handler(request):
        path = request.url.path
        if path == "/api/auth/login":
            return _ok({"access_token": "tok-1"})
        if path == "/api/auth/refresh":
            state["expired"] = False
            return _ok({"access_token": "tok-2"})
        if state["expired"]:
            return _ok({"detail": "Invalid or expired access token"}, status=401)
        return _ok([{"id": "m1"}])

    client, rec = _client(handler)
    result = await client.get("/api/materials")
    await client.aclose()

    assert result == [{"id": "m1"}]
    assert rec.paths() == [
        "/api/auth/login",
        "/api/materials",   # 401
        "/api/auth/refresh",
        "/api/materials",   # retried with the new token
    ]
    assert rec.auth_headers()[-1] == "Bearer tok-2"


@pytest.mark.asyncio
async def test_refresh_failure_falls_back_to_full_login():
    calls = {"login": 0}

    def handler(request):
        path = request.url.path
        if path == "/api/auth/login":
            calls["login"] += 1
            return _ok({"access_token": f"tok-{calls['login']}"})
        if path == "/api/auth/refresh":
            return _ok({"detail": "Refresh token missing"}, status=401)
        if request.headers.get("authorization") == "Bearer tok-1":
            return _ok({"detail": "Invalid or expired access token"}, status=401)
        return _ok({"ok": True})

    client, rec = _client(handler)
    assert await client.get("/api/materials") == {"ok": True}
    await client.aclose()
    assert calls["login"] == 2
    assert "/api/auth/refresh" in rec.paths()


@pytest.mark.asyncio
async def test_persistent_401_surfaces_rather_than_looping():
    def handler(request):
        if request.url.path in ("/api/auth/login", "/api/auth/refresh"):
            return _ok({"access_token": "tok"})
        return _ok({"detail": "User not found or inactive"}, status=401)

    client, rec = _client(handler)
    with pytest.raises(OrderHubError) as exc:
        await client.get("/api/materials")
    await client.aclose()

    # Exactly one retry — a revoked agent must fail fast, not spin.
    assert rec.paths().count("/api/materials") == 2
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_401s_reauthenticate_once():
    state = {"expired": True}

    def handler(request):
        path = request.url.path
        if path == "/api/auth/login":
            return _ok({"access_token": "tok-1"})
        if path == "/api/auth/refresh":
            state["expired"] = False
            return _ok({"access_token": "tok-2"})
        if state["expired"]:
            return _ok({"detail": "expired"}, status=401)
        return _ok({"ok": True})

    client, rec = _client(handler)
    await asyncio.gather(*(client.get(f"/api/materials/{i}") for i in range(5)))
    await client.aclose()

    # The lock collapses the stampede into a single refresh.
    assert rec.paths().count("/api/auth/refresh") == 1
    assert rec.paths().count("/api/auth/login") == 1


# ── error passthrough ──────────────────────────────────────

@pytest.mark.asyncio
async def test_403_detail_reaches_the_agent_verbatim():
    """A shop-scope denial must read as a permission error, not a tool crash."""
    def handler(request):
        if request.url.path == "/api/auth/login":
            return _ok({"access_token": "tok"})
        return _ok({"detail": "You do not have access to this shop"}, status=403)

    client, _ = _client(handler)
    with pytest.raises(OrderHubError) as exc:
        await client.get("/api/shops/abc/products")
    await client.aclose()

    assert exc.value.status_code == 403
    assert exc.value.detail == "You do not have access to this shop"
    assert "403" in str(exc.value)


@pytest.mark.asyncio
async def test_422_validation_detail_does_not_crash():
    def handler(request):
        if request.url.path == "/api/auth/login":
            return _ok({"access_token": "tok"})
        return _ok(
            {"detail": [{"loc": ["body", "qty"], "msg": "must be > 0"}]}, status=422
        )

    client, _ = _client(handler)
    with pytest.raises(OrderHubError) as exc:
        await client.post("/api/materials/x/receipts", {"qty": 0})
    await client.aclose()
    assert exc.value.status_code == 422
    assert "must be > 0" in exc.value.detail


@pytest.mark.asyncio
async def test_204_returns_none():
    def handler(request):
        if request.url.path == "/api/auth/login":
            return _ok({"access_token": "tok"})
        return httpx.Response(204)

    client, _ = _client(handler)
    assert await client.delete("/api/materials/x") is None
    await client.aclose()


# ── query params ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_unset_params_are_omitted_so_api_defaults_apply():
    def handler(request):
        if request.url.path == "/api/auth/login":
            return _ok({"access_token": "tok"})
        assert "search" not in request.url.params
        assert request.url.params["include_inactive"] == "false"
        return _ok([])

    client, _ = _client(handler)
    await client.get("/api/materials", search=None, include_inactive=False)
    await client.aclose()


def test_drop_none_keeps_falsy_values():
    # False and 0 are meaningful query values; only None means "unset".
    assert _drop_none({"a": None, "b": False, "c": 0}) == {"b": False, "c": 0}
    assert _drop_none({}) is None
    assert _drop_none(None) is None


def test_detail_of_handles_non_json_body():
    response = httpx.Response(502, text="upstream boom")
    assert _detail_of(response) == "upstream boom"
