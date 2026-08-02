"""Write tool surface — action logging (§5.8), BOM wipe protection (§5.5).

The two behaviours worth pinning are the ones layered on top of the REST
passthrough: nothing may mutate without leaving an action-log row, and no small
recipe edit may silently delete lines.
"""

import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from config import Config
from server import build_server
from tools_write import _diff_bom, BomLine

READ_TOOLS = {
    "list_shops", "list_materials", "get_material", "list_material_receipts",
    "list_material_movements", "list_receipts_by_invoice",
    "list_overhead_materials", "list_overhead_expenses",
    "list_products", "get_product", "get_product_bom", "compute_product_cost",
}
WRITE_TOOLS = {
    "create_material", "update_material", "archive_material",
    "record_material_receipt", "adjust_material_stock",
    "create_overhead_material", "record_overhead_expense",
    "set_product_bom", "add_bom_line", "remove_bom_line",
}

MATERIAL = {
    "id": "m1", "name": "Шкіра італійська чорна", "unit": "dm2", "currency": "UAH",
    "current_unit_cost": "500.0000", "stock_quantity": "10.00",
    "supplier_sku": "027515",
}


def _build(routes):
    """`routes` maps (METHOD, path) -> response or callable(request)->response."""
    config = Config(
        api_url="http://testserver", agent_email="agent@orderhub.dev",
        agent_password="s3cret", timeout_s=5.0,
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path == "/api/agent-actions":
            return httpx.Response(201, json={"id": "log1"})
        key = (request.method, request.url.path)
        if key not in routes:
            return httpx.Response(404, json={"detail": f"unrouted {key}"})
        value = routes[key]
        return value(request) if callable(value) else value

    mcp, client = build_server(config, transport=httpx.MockTransport(handler))
    return mcp, client, seen


def _logged(seen):
    """The bodies of every action-log write."""
    return [
        json.loads(r.content)
        for r in seen
        if r.url.path == "/api/agent-actions"
    ]


def _bom(*items):
    return {"items": list(items), "cost": [], "has_inactive_material": False}


def _line(material_id, qty, name=None):
    return {
        "material_id": material_id, "qty_per_unit": qty,
        "material_name": name or material_id, "notes": None,
        "material_unit": "dm2", "material_is_active": True,
    }


# ── registration ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_exact_registered_tool_surface():
    """Pins the whole surface: warehouse + catalog only.

    Orders, shipping, users, shops and finance are deliberately absent — every
    one has irreversible real-world side effects.
    """
    mcp, client, _ = _build({})
    names = {t.name for t in await mcp.list_tools()}
    await client.aclose()
    assert names == READ_TOOLS | WRITE_TOOLS


# ── action logging (§5.8) ──────────────────────────────────

@pytest.mark.asyncio
async def test_successful_write_is_logged_with_intent():
    routes = {
        ("POST", "/api/materials"): httpx.Response(
            201, json={**MATERIAL, "id": "new1"}
        ),
        ("GET", "/api/materials"): httpx.Response(200, json=[]),
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "create_material", {"name": "Нитка", "unit": "m", "currency": "UAH"}
    )
    await client.aclose()

    entries = _logged(seen)
    assert len(entries) == 1
    assert entries[0]["tool"] == "create_material"
    assert entries[0]["ok"] is True
    assert entries[0]["object_type"] == "material"
    assert entries[0]["object_id"] == "new1"
    assert entries[0]["arguments"]["name"] == "Нитка"


@pytest.mark.asyncio
async def test_failed_write_is_logged_then_reraised():
    """A rejected write must leave a trace — a repeated 403 is a signal."""
    routes = {
        ("GET", "/api/materials"): httpx.Response(200, json=[]),
        ("POST", "/api/materials"): httpx.Response(
            403, json={"detail": "You do not have permission to view this financial data"}
        ),
    }
    mcp, client, seen = _build(routes)
    with pytest.raises(ToolError):
        await mcp.call_tool(
            "create_material", {"name": "X", "unit": "m", "currency": "UAH"}
        )
    await client.aclose()

    entries = _logged(seen)
    assert len(entries) == 1
    assert entries[0]["ok"] is False
    assert "permission" in entries[0]["error"]


@pytest.mark.asyncio
async def test_broken_action_log_warns_but_does_not_fail_the_write():
    """The mutation already happened; reporting it as failed would be a lie."""
    config = Config(
        api_url="http://testserver", agent_email="a@b.dev",
        agent_password="p", timeout_s=5.0,
    )

    def handler(request):
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path == "/api/agent-actions":
            return httpx.Response(500, json={"detail": "log is down"})
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(201, json={**MATERIAL, "id": "new1"})

    mcp, client = build_server(config, transport=httpx.MockTransport(handler))
    result = await mcp.call_tool(
        "create_material", {"name": "Нитка", "unit": "m", "currency": "UAH"}
    )
    await client.aclose()
    assert "WARNING: action log write failed" in json.dumps(result, default=str)


@pytest.mark.asyncio
async def test_receipt_summary_reports_the_cost_movement():
    """The summary is what the owner reads — it must show cost before -> after."""
    routes = {
        ("GET", "/api/materials/m1"): httpx.Response(200, json=MATERIAL),
        ("POST", "/api/materials/m1/receipts"): httpx.Response(
            201,
            json={
                "material": {**MATERIAL, "current_unit_cost": "597.1429",
                             "stock_quantity": "35.00"},
                "receipt": {"id": "r1"},
            },
        ),
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "record_material_receipt",
        {"material_id": "m1", "qty": "25", "unit_cost": "700", "currency": "UAH"},
    )
    await client.aclose()

    entry = _logged(seen)[0]
    assert entry["object_id"] == "r1"
    assert "500.0000 -> 597.1429" in entry["summary"]
    assert "10.00 -> 35.00" in entry["summary"]


# ── input validation ───────────────────────────────────────

@pytest.mark.asyncio
async def test_bad_decimal_rejected_before_any_request():
    mcp, client, seen = _build({("GET", "/api/materials/m1"): httpx.Response(200, json=MATERIAL)})
    with pytest.raises(ToolError, match="decimal"):
        await mcp.call_tool(
            "record_material_receipt",
            {"material_id": "m1", "qty": "twenty", "unit_cost": "5", "currency": "UAH"},
        )
    await client.aclose()
    assert not [r for r in seen if r.method == "POST" and "receipts" in r.url.path]


@pytest.mark.asyncio
async def test_zero_delta_adjustment_rejected():
    mcp, client, _ = _build({("GET", "/api/materials/m1"): httpx.Response(200, json=MATERIAL)})
    with pytest.raises(ToolError, match="non-zero"):
        await mcp.call_tool(
            "adjust_material_stock",
            {"material_id": "m1", "delta": "0", "reason": "waste"},
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_unknown_adjustment_reason_rejected():
    mcp, client, _ = _build({})
    with pytest.raises(ToolError, match="adjustment"):
        await mcp.call_tool(
            "adjust_material_stock",
            {"material_id": "m1", "delta": "-1", "reason": "shrinkage"},
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_empty_material_update_rejected():
    mcp, client, _ = _build({})
    with pytest.raises(ToolError, match="Nothing to update"):
        await mcp.call_tool("update_material", {"material_id": "m1"})
    await client.aclose()


# ── duplicate-material guard ───────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_material_name_refused_with_the_existing_id():
    """Two rows for one real material split the weighted average permanently."""
    routes = {("GET", "/api/materials"): httpx.Response(200, json=[MATERIAL])}
    mcp, client, seen = _build(routes)
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool(
            "create_material",
            {"name": "шкіра італійська чорна", "unit": "dm2", "currency": "UAH"},
        )
    await client.aclose()
    assert "m1" in str(exc.value)  # tells the agent what to use instead
    assert not [r for r in seen if r.method == "POST" and r.url.path == "/api/materials"]


@pytest.mark.asyncio
async def test_duplicate_guard_is_overridable():
    routes = {
        ("GET", "/api/materials"): httpx.Response(200, json=[MATERIAL]),
        ("POST", "/api/materials"): httpx.Response(201, json={**MATERIAL, "id": "m2"}),
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "create_material",
        {
            "name": MATERIAL["name"], "unit": "dm2", "currency": "UAH",
            "allow_duplicate_name": True,
        },
    )
    await client.aclose()
    assert [r for r in seen if r.method == "POST" and r.url.path == "/api/materials"]


@pytest.mark.asyncio
async def test_duplicate_supplier_sku_refused_even_when_the_name_differs():
    """MAT-6, the case the name guard cannot catch: one material spelled two ways
    across two invoices. The article is the supplier's own key, so it wins."""
    routes = {("GET", "/api/materials"): httpx.Response(200, json=[MATERIAL])}
    mcp, client, seen = _build(routes)
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool(
            "create_material",
            {
                "name": "Шкіра чорна італ.",  # deliberately not MATERIAL["name"]
                "unit": "dm2", "currency": "UAH",
                "supplier_sku": MATERIAL["supplier_sku"],
            },
        )
    await client.aclose()
    assert "m1" in str(exc.value)  # tells the agent what to use instead
    assert MATERIAL["supplier_sku"] in str(exc.value)
    assert MATERIAL["name"] in str(exc.value)  # names the row it collided with
    assert not [r for r in seen if r.method == "POST" and r.url.path == "/api/materials"]


@pytest.mark.asyncio
async def test_supplier_sku_guard_searches_by_the_article():
    """The lookup must go out as search=<sku>. The REST search matches
    supplier_sku server-side (MAT-6); searching by name here would never find the
    collision."""
    captured = []

    def on_get(request):
        captured.append(request.url.params.get("search"))
        return httpx.Response(200, json=[])

    routes = {
        ("GET", "/api/materials"): on_get,
        ("POST", "/api/materials"): httpx.Response(201, json={**MATERIAL, "id": "m2"}),
    }
    mcp, client, _ = _build(routes)
    await mcp.call_tool(
        "create_material",
        {"name": "Нова шкіра", "unit": "dm2", "currency": "UAH", "supplier_sku": "032053"},
    )
    await client.aclose()
    assert "032053" in captured, f"expected a search by article, got {captured}"


@pytest.mark.asyncio
async def test_supplier_sku_guard_is_overridable():
    """Suppliers may genuinely reuse a code for an unrelated item."""
    routes = {
        ("GET", "/api/materials"): httpx.Response(200, json=[MATERIAL]),
        ("POST", "/api/materials"): httpx.Response(201, json={**MATERIAL, "id": "m2"}),
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "create_material",
        {
            "name": "Зовсім інша шкіра", "unit": "dm2", "currency": "UAH",
            "supplier_sku": MATERIAL["supplier_sku"],
            "allow_duplicate_sku": True,
        },
    )
    await client.aclose()
    assert [r for r in seen if r.method == "POST" and r.url.path == "/api/materials"]


@pytest.mark.asyncio
async def test_a_different_article_is_allowed():
    routes = {
        ("GET", "/api/materials"): httpx.Response(200, json=[MATERIAL]),
        ("POST", "/api/materials"): httpx.Response(201, json={**MATERIAL, "id": "m2"}),
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "create_material",
        {
            "name": "Шкіра Крейзі Хорс рожева", "unit": "dm2", "currency": "UAH",
            "supplier_sku": "032053",
        },
    )
    await client.aclose()
    assert [r for r in seen if r.method == "POST" and r.url.path == "/api/materials"]


@pytest.mark.asyncio
async def test_supplier_sku_reaches_the_payload_and_the_action_log():
    captured = {}

    def on_post(request):
        captured.update(json.loads(request.content))
        return httpx.Response(201, json={**MATERIAL, "id": "m2"})

    routes = {
        ("GET", "/api/materials"): httpx.Response(200, json=[]),
        ("POST", "/api/materials"): on_post,
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "create_material",
        {
            "name": "Шкіра Крейзі Хорс рожева", "unit": "dm2", "currency": "UAH",
            "supplier_sku": "032053",
        },
    )
    await client.aclose()
    assert captured["supplier_sku"] == "032053"
    assert _logged(seen)[0]["arguments"]["supplier_sku"] == "032053"


@pytest.mark.asyncio
async def test_update_material_can_set_the_supplier_sku():
    """The back-fill path for the materials that predate the column."""
    captured = {}

    def on_patch(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=MATERIAL)

    routes = {("PATCH", "/api/materials/m1"): on_patch}
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "update_material", {"material_id": "m1", "supplier_sku": "027515"}
    )
    await client.aclose()
    assert captured == {"supplier_sku": "027515"}, (
        f"only the named field may be patched, got {captured}"
    )
    assert _logged(seen)[0]["arguments"]["supplier_sku"] == "027515"


@pytest.mark.asyncio
async def test_similar_but_different_name_is_allowed():
    routes = {
        ("GET", "/api/materials"): httpx.Response(200, json=[MATERIAL]),
        ("POST", "/api/materials"): httpx.Response(201, json={**MATERIAL, "id": "m2"}),
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "create_material",
        {"name": "Шкіра італійська коричнева", "unit": "dm2", "currency": "UAH"},
    )
    await client.aclose()
    assert [r for r in seen if r.method == "POST" and r.url.path == "/api/materials"]


# ── BOM wipe protection (§5.5) ─────────────────────────────

@pytest.mark.asyncio
async def test_destructive_replace_refused_without_confirmation():
    current = _bom(_line("m1", "5.00", "Leather"), _line("m2", "0.50", "Plywood"))
    routes = {("GET", "/api/products/p1/bom"): httpx.Response(200, json=current)}
    mcp, client, seen = _build(routes)

    with pytest.raises(ToolError) as exc:
        await mcp.call_tool(
            "set_product_bom",
            {"product_id": "p1", "items": [{"material_id": "m1", "qty_per_unit": "5.00"}]},
        )
    await client.aclose()

    assert "Plywood" in str(exc.value)          # names what would be lost
    assert "confirm_replace=True" in str(exc.value)
    assert not [r for r in seen if r.method == "PUT"]
    assert not _logged(seen)                     # nothing happened, nothing logged


@pytest.mark.asyncio
async def test_confirmed_replace_proceeds():
    current = _bom(_line("m1", "5.00", "Leather"), _line("m2", "0.50", "Plywood"))
    routes = {
        ("GET", "/api/products/p1/bom"): httpx.Response(200, json=current),
        ("PUT", "/api/products/p1/bom"): httpx.Response(
            200, json=_bom(_line("m1", "5.00", "Leather"))
        ),
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "set_product_bom",
        {
            "product_id": "p1",
            "items": [{"material_id": "m1", "qty_per_unit": "5.00"}],
            "confirm_replace": True,
        },
    )
    await client.aclose()
    assert [r for r in seen if r.method == "PUT"]
    assert _logged(seen)[0]["tool"] == "set_product_bom"


@pytest.mark.asyncio
async def test_purely_additive_replace_needs_no_confirmation():
    """Adding a line destroys nothing, so it should not demand a ceremony."""
    current = _bom(_line("m1", "5.00", "Leather"))
    routes = {
        ("GET", "/api/products/p1/bom"): httpx.Response(200, json=current),
        ("PUT", "/api/products/p1/bom"): httpx.Response(200, json=current),
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "set_product_bom",
        {
            "product_id": "p1",
            "items": [
                {"material_id": "m1", "qty_per_unit": "5.00"},
                {"material_id": "m2", "qty_per_unit": "1.00"},
            ],
        },
    )
    await client.aclose()
    assert [r for r in seen if r.method == "PUT"]


@pytest.mark.asyncio
async def test_add_bom_line_preserves_every_other_line():
    current = _bom(_line("m1", "5.00", "Leather"), _line("m2", "0.50", "Plywood"))
    captured = {}

    def put(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=current)

    routes = {
        ("GET", "/api/products/p1/bom"): httpx.Response(200, json=current),
        ("PUT", "/api/products/p1/bom"): put,
    }
    mcp, client, _ = _build(routes)
    await mcp.call_tool(
        "add_bom_line",
        {"product_id": "p1", "material_id": "m3", "qty_per_unit": "2.00"},
    )
    await client.aclose()

    sent = {i["material_id"]: i["qty_per_unit"] for i in captured["body"]["items"]}
    assert sent == {"m1": "5.00", "m2": "0.50", "m3": "2.00"}


@pytest.mark.asyncio
async def test_add_bom_line_updates_an_existing_material_in_place():
    current = _bom(_line("m1", "5.00", "Leather"))
    captured = {}

    def put(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=current)

    routes = {
        ("GET", "/api/products/p1/bom"): httpx.Response(200, json=current),
        ("PUT", "/api/products/p1/bom"): put,
    }
    mcp, client, _ = _build(routes)
    await mcp.call_tool(
        "add_bom_line",
        {"product_id": "p1", "material_id": "m1", "qty_per_unit": "7.50"},
    )
    await client.aclose()

    # One line, not a duplicate — the API rejects duplicate material_ids.
    assert captured["body"]["items"] == [
        {"material_id": "m1", "qty_per_unit": "7.50", "notes": None}
    ]


@pytest.mark.asyncio
async def test_remove_bom_line_drops_exactly_one():
    current = _bom(_line("m1", "5.00", "Leather"), _line("m2", "0.50", "Plywood"))
    captured = {}

    def put(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=current)

    routes = {
        ("GET", "/api/products/p1/bom"): httpx.Response(200, json=current),
        ("PUT", "/api/products/p1/bom"): put,
    }
    mcp, client, _ = _build(routes)
    await mcp.call_tool("remove_bom_line", {"product_id": "p1", "material_id": "m2"})
    await client.aclose()

    assert [i["material_id"] for i in captured["body"]["items"]] == ["m1"]


@pytest.mark.asyncio
async def test_remove_absent_material_is_an_error_not_a_silent_rewrite():
    current = _bom(_line("m1", "5.00", "Leather"))
    routes = {("GET", "/api/products/p1/bom"): httpx.Response(200, json=current)}
    mcp, client, seen = _build(routes)

    with pytest.raises(ToolError, match="not in this recipe"):
        await mcp.call_tool("remove_bom_line", {"product_id": "p1", "material_id": "m9"})
    await client.aclose()
    assert not [r for r in seen if r.method == "PUT"]


# ── diff helper ────────────────────────────────────────────

def test_diff_detects_removal_addition_and_quantity_change():
    old = [_line("m1", "5.00", "Leather"), _line("m2", "0.50", "Plywood")]
    new = [
        BomLine(material_id="m1", qty_per_unit="7.00"),
        BomLine(material_id="m3", qty_per_unit="1.00"),
    ]
    diff = _diff_bom(old, new)
    assert any("Plywood" in r for r in diff["removed"])
    assert any("m3" in a for a in diff["added"])
    assert any("5.00 -> 7.00" in c for c in diff["changed"])


def test_diff_ignores_decimal_formatting_noise():
    """'5.00' and '5' are the same quantity — not a change to confirm."""
    old = [_line("m1", "5.00", "Leather")]
    new = [BomLine(material_id="m1", qty_per_unit="5")]
    assert _diff_bom(old, new)["changed"] == []
