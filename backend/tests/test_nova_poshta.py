"""NP-FIX-2 — Service-level tests for NovaPoshtaClient.

Mocks httpx.AsyncClient at the module boundary so no real HTTP fires.
Covers the _post retry/translation contract and the small wrapper methods.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from tenacity import wait_none

from services.nova_poshta import NovaPoshtaAPIError, NovaPoshtaClient


def _response(json_payload):
    r = MagicMock()
    r.json.return_value = json_payload
    r.raise_for_status = MagicMock()
    return r


def _async_client_cm(post_mock):
    """Build a mock context manager that returns a client whose .post is post_mock."""
    client = MagicMock()
    client.post = post_mock
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, client


@pytest.mark.asyncio
async def test_post_returns_data_array_on_success():
    post = AsyncMock(return_value=_response({"success": True, "data": [{"x": 1}]}))
    cm, _ = _async_client_cm(post)

    with patch("services.nova_poshta.httpx.AsyncClient", return_value=cm):
        client = NovaPoshtaClient("api-key")
        result = await client._post("Address", "getCities", {})

    assert result == [{"x": 1}]
    assert post.await_count == 1


@pytest.mark.asyncio
async def test_post_raises_nova_poshta_api_error_on_success_false():
    post = AsyncMock(return_value=_response({"success": False, "errors": ["Invalid API key"]}))
    cm, _ = _async_client_cm(post)

    with patch("services.nova_poshta.httpx.AsyncClient", return_value=cm):
        client = NovaPoshtaClient("api-key")
        with pytest.raises(NovaPoshtaAPIError) as exc:
            await client._post("Address", "getCities", {})

    assert "Invalid API key" in str(exc.value)


@pytest.mark.asyncio
async def test_post_does_not_retry_on_nova_poshta_api_error():
    """Business-level failures must NOT trigger tenacity retries."""
    post = AsyncMock(return_value=_response({"success": False, "errors": ["bad request"]}))
    cm, client_inner = _async_client_cm(post)

    with patch("services.nova_poshta.httpx.AsyncClient", return_value=cm):
        client = NovaPoshtaClient("api-key")
        with pytest.raises(NovaPoshtaAPIError):
            await client._post("Address", "getCities", {})

    # _post is invoked exactly once — tenacity does not retry on NovaPoshtaAPIError.
    assert client_inner.post.await_count == 1


@pytest.mark.asyncio
async def test_post_retries_on_httpx_http_error(monkeypatch):
    """Network-level failures DO trigger tenacity retries (configured to 3 attempts)."""
    # Neutralize tenacity's exponential wait so the test runs in milliseconds.
    monkeypatch.setattr(NovaPoshtaClient._post.retry, "wait", wait_none())

    success_response = _response({"success": True, "data": [{"ok": True}]})
    post = AsyncMock(side_effect=[
        httpx.HTTPError("net1"),
        httpx.HTTPError("net2"),
        success_response,
    ])
    cm, client_inner = _async_client_cm(post)

    with patch("services.nova_poshta.httpx.AsyncClient", return_value=cm):
        client = NovaPoshtaClient("api-key")
        result = await client._post("Address", "getCities", {})

    assert result == [{"ok": True}]
    assert client_inner.post.await_count == 3


@pytest.mark.asyncio
async def test_get_cities_passes_query_in_props():
    client = NovaPoshtaClient("api-key")

    with patch.object(NovaPoshtaClient, "_post", new=AsyncMock(return_value=[])) as mock_post:
        await client.get_cities("Київ")
        await client.get_cities("")

    assert mock_post.await_count == 2
    first_call = mock_post.await_args_list[0]
    second_call = mock_post.await_args_list[1]

    assert first_call.args == ("Address", "getCities", {"FindByString": "Київ"})
    assert second_call.args == ("Address", "getCities", {})


@pytest.mark.asyncio
async def test_get_warehouses_passes_city_ref_and_optional_query():
    client = NovaPoshtaClient("api-key")

    with patch.object(NovaPoshtaClient, "_post", new=AsyncMock(return_value=[])) as mock_post:
        await client.get_warehouses("city-ref-1", "вул. Хрещатик")
        await client.get_warehouses("city-ref-2")

    with_query = mock_post.await_args_list[0]
    without_query = mock_post.await_args_list[1]

    assert with_query.args == (
        "Address",
        "getWarehouses",
        {"CityRef": "city-ref-1", "FindByString": "вул. Хрещатик"},
    )
    assert without_query.args == (
        "Address",
        "getWarehouses",
        {"CityRef": "city-ref-2"},
    )


@pytest.mark.asyncio
async def test_create_internet_document_returns_first_item():
    client = NovaPoshtaClient("api-key")

    with patch.object(
        NovaPoshtaClient,
        "_post",
        new=AsyncMock(return_value=[{"IntDocNumber": "20450123456789", "Ref": "ref-1"}]),
    ):
        result = await client.create_internet_document({"foo": "bar"})

    assert result == {"IntDocNumber": "20450123456789", "Ref": "ref-1"}


@pytest.mark.asyncio
async def test_create_internet_document_raises_on_empty_response():
    client = NovaPoshtaClient("api-key")

    with patch.object(NovaPoshtaClient, "_post", new=AsyncMock(return_value=[])):
        with pytest.raises(Exception, match="empty response"):
            await client.create_internet_document({"foo": "bar"})
