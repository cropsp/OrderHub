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
    "list_receipts_by_invoice",
    "list_overhead_materials",
    "list_overhead_expenses",
    "list_products",
    "get_product",
    "get_product_bom",
    "compute_product_cost",
    "check_parcel_delivery",
    "list_packaging",
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
    # Subset, not equality — write tools share the same server. The exact
    # registered surface is pinned in test_tools_write.py.
    assert EXPECTED_TOOLS <= names


@pytest.mark.asyncio
async def test_every_tool_has_a_description():
    """Docstrings are the agent's only guidance about domain rules."""
    mcp, client, _ = _build(lambda r: httpx.Response(200, json=[]))
    tools = await mcp.list_tools()
    await client.aclose()
    for tool in tools:
        assert tool.description and len(tool.description) > 40, tool.name


@pytest.mark.asyncio
async def test_read_tools_do_not_write_to_the_action_log():
    """Only writes are logged — a read sweep must not spam the audit trail."""
    mcp, client, seen = _build(lambda r: httpx.Response(200, json={}))
    for name in sorted(EXPECTED_TOOLS):
        tool = next(t for t in await mcp.list_tools() if t.name == name)
        await mcp.call_tool(name, {a: "x" for a in tool.inputSchema.get("required", [])})
    await client.aclose()
    assert not [r for r in seen if r.url.path == "/api/agent-actions"]


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
        (
            "list_receipts_by_invoice",
            {"invoice_no": "1996637412"},
            "/api/receipts/by-invoice",
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
        ("check_parcel_delivery", {}, "/api/westernbid/tracking"),
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
async def test_invoice_no_is_forwarded_as_a_query_param():
    """MAT-6 — the invoice number selects the lines; dropping it would silently
    return whatever the endpoint defaults to."""
    captured = {}

    def handler(request):
        captured["invoice_no"] = request.url.params.get("invoice_no")
        return httpx.Response(
            200,
            json={
                "invoice_no": "1996637412",
                "material_receipts": [],
                "overhead_receipts": [],
            },
        )

    mcp, client, _ = _build(handler)
    await mcp.call_tool("list_receipts_by_invoice", {"invoice_no": "1996637412"})
    await client.aclose()
    assert captured["invoice_no"] == "1996637412"


@pytest.mark.asyncio
async def test_invoice_view_passes_both_blocks_through_untouched():
    """A real invoice mixes direct materials with overhead lines. Both blocks must
    reach the agent verbatim — no merging, no totalling (tools are passthroughs)."""
    body = {
        "invoice_no": "1996637412",
        "material_receipts": [
            {"material_name": "Шкіра Крейзі Хорс AN чорна", "qty": "100.00",
             "unit_cost": "12.7539", "currency": "UAH"}
        ],
        "overhead_receipts": [
            {"overhead_material_name": "Послуга порізки шкіри",
             "total_cost": "80.00", "currency": "UAH"}
        ],
    }
    mcp, client, _ = _build(lambda r: httpx.Response(200, json=body))
    result = await mcp.call_tool(
        "list_receipts_by_invoice", {"invoice_no": "1996637412"}
    )
    await client.aclose()
    assert _payload(result) == body


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


@pytest.mark.asyncio
async def test_compute_product_cost_passes_the_target_currency():
    """FX-CONVERSION: `in_currency` reaches the backend as the `in` query param —
    which is what lets the agent answer "what does this cost in USD"."""
    mcp, client, seen = _build(
        lambda r: httpx.Response(200, json={"basis": [], "converted": None})
    )
    await mcp.call_tool(
        "compute_product_cost", {"product_id": "p1", "in_currency": "USD"}
    )
    await client.aclose()

    cost_calls = [r for r in seen if r.url.path == "/api/products/p1/bom/cost"]
    assert len(cost_calls) == 1
    assert cost_calls[0].url.params.get("in") == "USD"


@pytest.mark.asyncio
async def test_compute_product_cost_omits_the_param_when_unset():
    """No target currency means the pre-FX behaviour: basis only, no conversion."""
    mcp, client, seen = _build(
        lambda r: httpx.Response(200, json={"basis": [], "converted": None})
    )
    await mcp.call_tool("compute_product_cost", {"product_id": "p1"})
    await client.aclose()

    cost_calls = [r for r in seen if r.url.path == "/api/products/p1/bom/cost"]
    assert "in" not in cost_calls[0].url.params


# ── list_packaging (WH-4) ──────────────────────────────────
#
# The one read tool that merges two endpoints. It has to, because a box's
# geometry and its cost live apart on purpose: PackagingBoxRead carries no cost
# field, so that the un-cost-gated packaging router (and ParcelEstimate and
# OrderResponse, which nest it) stay off the money surface. Joining in the tool
# keeps the money behind view_costs where the materials router put it.

BOX_ROW = {
    "id": "b1", "material_id": "bm1", "name": "Коробка (120 x 100 x 80), бурая",
    "packaging_type": "BOX", "inner_length_mm": 120, "inner_width_mm": 100,
    "inner_height_mm": 80, "max_weight_g": 5000, "tare_weight_g": 42,
    "stock_quantity": "620.00", "low_stock_threshold": "5.00",
    "material_is_active": True,
}

BOX_MATERIAL = {
    "id": "bm1", "name": "Коробка (120 x 100 x 80), бурая", "unit": "pcs",
    "currency": "UAH", "current_unit_cost": "8.4000", "stock_quantity": "620.00",
    "supplier_sku": "140", "supplier_name": "Упаковочки", "is_active": True,
}


def _packaging_routes(boxes=None, materials=None):
    def handler(request):
        if request.url.path == "/api/packaging-boxes":
            return httpx.Response(200, json=boxes if boxes is not None else [BOX_ROW])
        if request.url.path == "/api/materials":
            return httpx.Response(
                200, json=materials if materials is not None else [BOX_MATERIAL]
            )
        return httpx.Response(404, json={"detail": f"unrouted {request.url.path}"})

    return handler


@pytest.mark.asyncio
async def test_list_packaging_joins_geometry_to_its_material():
    """One row per box: the geometry, plus the four money/supplier fields the
    packaging endpoint deliberately does not carry."""
    mcp, client, _ = _build(_packaging_routes())
    result = await mcp.call_tool("list_packaging", {})
    await client.aclose()

    row = _payload(result)[0]
    # geometry, untouched
    assert row["inner_length_mm"] == 120
    assert row["material_id"] == "bm1"
    # merged from the cost-gated materials endpoint
    assert row["current_unit_cost"] == "8.4000"
    assert row["currency"] == "UAH"
    assert row["supplier_sku"] == "140"
    assert row["supplier_name"] == "Упаковочки"


@pytest.mark.asyncio
async def test_list_packaging_reads_archived_materials_regardless_of_the_flag():
    """`include_archived` decides which BOXES are listed. The materials fetch
    always includes inactive ones, or an archived box the caller did ask for
    would come back stripped of its cost."""
    mcp, client, seen = _build(_packaging_routes())
    await mcp.call_tool("list_packaging", {"include_archived": True})
    await client.aclose()

    boxes = next(r for r in seen if r.url.path == "/api/packaging-boxes")
    materials = next(r for r in seen if r.url.path == "/api/materials")
    assert boxes.url.params.get("include_archived") == "true"
    assert materials.url.params.get("include_inactive") == "true"
    assert materials.url.params.get("category") == "PACKAGING"


@pytest.mark.asyncio
async def test_list_packaging_defaults_to_active_boxes_only():
    mcp, client, seen = _build(_packaging_routes())
    await mcp.call_tool("list_packaging", {})
    await client.aclose()

    boxes = next(r for r in seen if r.url.path == "/api/packaging-boxes")
    assert boxes.url.params.get("include_archived") == "false"


@pytest.mark.asyncio
async def test_list_packaging_degrades_loudly_when_the_cost_half_is_denied():
    """view_costs revoked: the geometry is still worth returning, but the agent
    must be told the money is missing rather than reading absent as zero."""
    def handler(request):
        if request.url.path == "/api/packaging-boxes":
            return httpx.Response(200, json=[BOX_ROW])
        return httpx.Response(
            403, json={"detail": "You do not have permission to view this financial data"}
        )

    mcp, client, _ = _build(handler)
    result = await mcp.call_tool("list_packaging", {})
    await client.aclose()

    text = result[0][0].text if isinstance(result, tuple) else result[0].text
    assert text.startswith("WARNING:")
    assert "permission" in text
    assert "Коробка (120 x 100 x 80), бурая" in text  # geometry still delivered
