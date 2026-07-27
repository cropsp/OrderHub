"""Read tool surface — registration, endpoint mapping, error surfacing.

The assertion that matters here is that every tool is a passthrough to the
existing REST API (MCP-WAREHOUSE §5.4). If a tool ever grew its own query or
its own arithmetic, the guards in backend/tests/test_money_field_completeness.py
would stop covering it.
"""

import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from config import Config
from server import build_server

EXPECTED_TOOLS = {
    "list_shops",
    "list_materials",
    "get_material",
    "list_material_receipts",
    "list_material_movements",
    "list_overhead_materials",
    "list_overhead_expenses",
    "list_products",
    "get_product",
    "get_product_bom",
    "compute_product_cost",
}


def _build(handler):
    """Build the real server against a mock transport, recording every request."""
    config = Config(
        api_url="http://testserver",
        agent_email="agent@orderhub.dev",
        agent_password="s3cret",
        timeout_s=5.0,
    )
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "tok"})
        return handler(request)

    mcp, client = build_server(config, transport=httpx.MockTransport(recording))
    return mcp, client, seen


def _payload(result):
    """Extract the tool's text output across FastMCP return shapes."""
    blocks = result[0] if isinstance(result, tuple) else result
    if isinstance(blocks, dict):
        return blocks
    return json.loads(blocks[0].text)


@pytest.mark.asyncio
async def test_all_read_tools_registered():
    mcp, client, _ = _build(lambda r: httpx.Response(200, json=[]))
    names = {tool.name for tool in await mcp.list_tools()}
    await client.aclose()
    assert names == EXPECTED_TOOLS


@pytest.mark.asyncio
async def test_every_tool_has_a_description():
    """Docstrings are the agent's only guidance about domain rules."""
    mcp, client, _ = _build(lambda r: httpx.Response(200, json=[]))
    tools = await mcp.list_tools()
    await client.aclose()
    for tool in tools:
        assert tool.description and len(tool.description) > 40, tool.name


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool,args,expected_path",
    [
        ("list_shops", {}, "/api/shops"),
        ("list_materials", {}, "/api/materials"),
        ("get_material", {"material_id": "m1"}, "/api/materials/m1"),
        (
            "list_material_receipts",
            {"material_id": "m1"},
            "/api/materials/m1/receipts",
        ),
        (
            "list_material_movements",
            {"material_id": "m1"},
            "/api/materials/m1/movements",
        ),
        ("list_overhead_materials", {}, "/api/overhead-materials"),
        (
            "list_overhead_expenses",
            {"overhead_id": "o1"},
            "/api/overhead-materials/o1/receipts",
        ),
        ("list_products", {"shop_id": "s1"}, "/api/shops/s1/products"),
        ("get_product", {"product_id": "p1"}, "/api/products/p1"),
        ("get_product_bom", {"product_id": "p1"}, "/api/products/p1/bom"),
        ("compute_product_cost", {"product_id": "p1"}, "/api/products/p1/bom/cost"),
    ],
)
async def test_tool_maps_to_its_endpoint(tool, args, expected_path):
    mcp, client, seen = _build(lambda r: httpx.Response(200, json={"ok": True}))
    await mcp.call_tool(tool, args)
    await client.aclose()
    assert [r.url.path for r in seen if r.url.path != "/api/auth/login"] == [
        expected_path
    ]


@pytest.mark.asyncio
async def test_tools_use_get_only():
    """Read tools must never mutate — MCP-1 is the read-only surface."""
    mcp, client, seen = _build(lambda r: httpx.Response(200, json={}))
    for name in sorted(EXPECTED_TOOLS):
        tool = next(t for t in await mcp.list_tools() if t.name == name)
        required = tool.inputSchema.get("required", [])
        await mcp.call_tool(name, {arg: "x" for arg in required})
    await client.aclose()
    assert {r.method for r in seen if r.url.path != "/api/auth/login"} == {"GET"}


@pytest.mark.asyncio
async def test_response_body_reaches_the_agent_unmodified():
    """Money text must not be re-rounded or re-formatted on the way through."""
    body = [{"currency": "UAH", "amount": "597.1429"}]
    mcp, client, _ = _build(lambda r: httpx.Response(200, json=body))
    result = await mcp.call_tool("compute_product_cost", {"product_id": "p1"})
    await client.aclose()
    assert _payload(result) == body


@pytest.mark.asyncio
async def test_search_filter_is_forwarded():
    captured = {}

    def handler(request):
        captured["search"] = request.url.params.get("search")
        return httpx.Response(200, json=[])

    mcp, client, _ = _build(handler)
    await mcp.call_tool("list_materials", {"search": "шкіра"})
    await client.aclose()
    assert captured["search"] == "шкіра"


@pytest.mark.asyncio
async def test_permission_error_is_reported_to_the_agent():
    """A shop-scope denial must reach the agent as readable text.

    FastMCP wraps a raised exception in ToolError; the protocol layer turns that
    into an `isError` result carrying the message, so the agent learns it may not
    touch this shop rather than retrying blindly.
    """
    def handler(request):
        return httpx.Response(
            403, json={"detail": "You do not have access to this shop"}
        )

    mcp, client, _ = _build(handler)
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool("list_products", {"shop_id": "s1"})
    await client.aclose()
    assert "You do not have access to this shop" in str(exc.value)
    assert "403" in str(exc.value)
