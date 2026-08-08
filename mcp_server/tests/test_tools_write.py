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
    "check_parcel_delivery", "list_packaging",
}
WRITE_TOOLS = {
    "create_material", "update_material", "archive_material",
    "record_material_receipt", "adjust_material_stock",
    "create_overhead_material", "record_overhead_expense",
    "set_product_bom", "add_bom_line", "remove_bom_line",
    "import_etsy_statement",
    "create_packaging_box", "update_packaging_box",
}

MATERIAL = {
    "id": "m1", "name": "Шкіра італійська чорна", "unit": "dm2", "currency": "UAH",
    "current_unit_cost": "500.0000", "stock_quantity": "10.00",
    "supplier_sku": "027515",
}

BOX = {
    "id": "b1", "material_id": "bm1", "name": "Коробка (120 x 100 x 80), бурая",
    "packaging_type": "BOX", "inner_length_mm": 120, "inner_width_mm": 100,
    "inner_height_mm": 80, "max_thickness_mm": None, "max_weight_g": 5000,
    "tare_weight_g": 42, "sort_order": 0, "stock_quantity": "0.00",
    "low_stock_threshold": "5.00", "material_is_active": True,
    "created_at": "2026-08-08T10:00:00", "updated_at": "2026-08-08T10:00:00",
}

BOX_GEOMETRY = {
    "name": "Коробка (120 x 100 x 80), бурая", "inner_length_mm": 120,
    "inner_width_mm": 100, "inner_height_mm": 80, "max_weight_g": 5000,
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
    """Pins the whole surface: warehouse + catalog, plus one read-only shipping tool.

    Orders, users, shops and finance are deliberately absent — every one has
    irreversible real-world side effects. `check_parcel_delivery` (WB-TRACK-1) is
    the single exception to the warehouse/catalog scope and earns it by being a
    pure read of carrier status: it mutates nothing here or at Nova Poshta.
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


# ── STATEMENT-IMPORT: statement upload ─────────────────────

STATEMENT_REPORT = {
    "dry_run": True,
    "period": "2026-04",
    "source_filename": "etsy_statement_2026_4.csv",
    "file_sha256": "abc123",
    "identical_file": False,
    "lines_imported": 343,
    "lines_replaced": 0,
    "orders_matched": 18,
    "orders_unmatched": 6,
    "unmatched_orders": [],
    "fee_overrides": [],
    "credit_only_orders": [],
    "ads_overhead_amount": "145.56",
    "account_fee_overhead_amount": "7.30",
    "checksum": {
        "stored_line_count": 343,
        "booked_cost_total": "306.46",
        "platform_fee_total": "153.60",
        "unclassified_buckets": [],
        "balanced": True,
    },
    "sales_count": 24,
    "statement_base_amount": "949.69",
    "refunds_count": 1,
    "refunds_amount": "-34.23",
    "deposits_count": 4,
    "deposits_amount": "812.40",
}

#: What the API answers when the tool asks for a real write.
STATEMENT_REPORT_BOOKED = {**STATEMENT_REPORT, "dry_run": False}

STATEMENT_CSV = (
    'Date,Type,Title,Info,Currency,Amount,"Fees & Taxes",Net,"Tax Details"\n'
    '"April 10, 2026",Fee,"Processing fee","Order #4026053403",USD,--,-$2.00,-$2.00,--\n'
)


def _statement_file(tmp_path, name="etsy_statement_2026_4.csv"):
    path = tmp_path / name
    path.write_text(STATEMENT_CSV, encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_statement_is_uploaded_as_multipart_not_a_json_argument(tmp_path):
    mcp, client, seen = _build(
        {("POST", "/api/imports/etsy-statement"): httpx.Response(200, json=STATEMENT_REPORT)}
    )
    path = _statement_file(tmp_path)

    await mcp.call_tool(
        "import_etsy_statement", {"shop_id": "shop-1", "file_path": str(path)}
    )

    upload = next(r for r in seen if r.url.path == "/api/imports/etsy-statement")
    assert upload.headers["content-type"].startswith("multipart/form-data")
    body = upload.content.decode()
    assert "etsy_statement_2026_4.csv" in body
    assert "Processing fee" in body, "the file's bytes must reach the API"
    assert 'name="shop_id"' in body and "shop-1" in body


@pytest.mark.asyncio
async def test_statement_contents_never_reach_the_action_log(tmp_path):
    """The statement is financial + PII data. Only the path is recorded — a CSV
    passed as a tool argument would be persisted verbatim in
    agent_action_log.arguments."""
    mcp, client, seen = _build(
        {("POST", "/api/imports/etsy-statement"): httpx.Response(200, json=STATEMENT_REPORT)}
    )
    path = _statement_file(tmp_path)

    await mcp.call_tool(
        "import_etsy_statement", {"shop_id": "shop-1", "file_path": str(path)}
    )

    entry = _logged(seen)[0]
    assert entry["tool"] == "import_etsy_statement"
    assert entry["ok"] is True
    # dry_run IS logged: whether a call wrote or only rehearsed is the most
    # important thing about it in the trail.
    assert set(entry["arguments"]) == {"shop_id", "file_path", "dry_run"}
    assert "Processing fee" not in json.dumps(entry)
    assert "Order #4026053403" not in json.dumps(entry)


@pytest.mark.asyncio
async def test_statement_rehearses_unless_told_otherwise(tmp_path):
    """The tool defaults to a dry run — an agent cannot book a statement the
    operator has not seen a preview of without saying so explicitly."""
    mcp, client, seen = _build(
        {("POST", "/api/imports/etsy-statement"): httpx.Response(200, json=STATEMENT_REPORT)}
    )
    path = _statement_file(tmp_path)

    result = await mcp.call_tool(
        "import_etsy_statement", {"shop_id": "shop-1", "file_path": str(path)}
    )

    upload = next(r for r in seen if r.url.path == "/api/imports/etsy-statement")
    body = upload.content.decode()
    assert 'name="dry_run"' in body and "true" in body

    text = str(result)
    assert "DRY RUN" in text and "nothing written" in text
    assert "dry_run=False" in text, "must say how to actually book it"


@pytest.mark.asyncio
async def test_statement_books_only_on_an_explicit_dry_run_false(tmp_path):
    mcp, client, seen = _build(
        {
            ("POST", "/api/imports/etsy-statement"): httpx.Response(
                200, json=STATEMENT_REPORT_BOOKED
            )
        }
    )
    path = _statement_file(tmp_path)

    result = await mcp.call_tool(
        "import_etsy_statement",
        {"shop_id": "shop-1", "file_path": str(path), "dry_run": False},
    )

    upload = next(r for r in seen if r.url.path == "/api/imports/etsy-statement")
    body = upload.content.decode()
    assert 'name="dry_run"' in body
    assert body.split('name="dry_run"')[1].split("--")[0].strip().endswith("false")

    text = str(result)
    assert "DRY RUN" not in text
    assert "booked" in text


@pytest.mark.asyncio
async def test_statement_summary_reports_what_was_booked(tmp_path):
    mcp, client, seen = _build(
        {
            ("POST", "/api/imports/etsy-statement"): httpx.Response(
                200, json=STATEMENT_REPORT_BOOKED
            )
        }
    )
    path = _statement_file(tmp_path)

    result = await mcp.call_tool(
        "import_etsy_statement",
        {"shop_id": "shop-1", "file_path": str(path), "dry_run": False},
    )
    text = str(result)

    assert "2026-04" in text
    assert "18 orders priced" in text
    assert "6 unmatched" in text
    assert "145.56" in text and "7.30" in text


@pytest.mark.asyncio
async def test_missing_file_is_refused_before_any_request(tmp_path):
    mcp, client, seen = _build({})

    with pytest.raises(Exception, match="No file at"):
        await mcp.call_tool(
            "import_etsy_statement",
            {"shop_id": "shop-1", "file_path": str(tmp_path / "nope.csv")},
        )

    assert not [r for r in seen if r.url.path == "/api/imports/etsy-statement"]
    assert _logged(seen) == [], "nothing was attempted, so nothing is logged"


@pytest.mark.asyncio
async def test_non_csv_is_refused(tmp_path):
    mcp, client, seen = _build({})
    path = _statement_file(tmp_path, name="statement.xlsx")

    with pytest.raises(Exception, match="Expected a .csv"):
        await mcp.call_tool(
            "import_etsy_statement", {"shop_id": "shop-1", "file_path": str(path)}
        )


@pytest.mark.asyncio
async def test_a_rejected_statement_is_logged_as_a_failed_attempt(tmp_path):
    """The API aborts on any row it cannot classify. That refusal is signal, so
    it is recorded and the message is raised verbatim."""
    detail = (
        "etsy_statement_2026_4.csv row 12: unknown Type 'Chargeback' "
        "[Type='Chargeback' Title='Disputed' Info='Order #4026053403']"
    )
    mcp, client, seen = _build(
        {
            ("POST", "/api/imports/etsy-statement"): httpx.Response(
                400, json={"detail": detail}
            )
        }
    )
    path = _statement_file(tmp_path)

    with pytest.raises(Exception, match="Chargeback"):
        await mcp.call_tool(
            "import_etsy_statement", {"shop_id": "shop-1", "file_path": str(path)}
        )

    entry = _logged(seen)[0]
    assert entry["ok"] is False
    assert "Chargeback" in entry["error"]


# ── packaging (WH-4) ───────────────────────────────────────
#
# A box is a geometry row plus a Material. Three of the material's fields have no
# home on PackagingBoxCreate (which is extra="forbid", so sending them there is a
# 422), so the tool composes two requests. What these tests pin is that the
# composition is honest: the right field goes to the right endpoint, a re-run of
# a catalog import is refused rather than duplicated, and a half-applied pair is
# never reported as a clean success.

BOX_CREATED = {**BOX, "id": "b9", "material_id": "bm9"}


def _create_routes(materials=None, boxes=None, created=None, patch=None):
    """Routes for a create: both dedup probes plus the two writes."""
    return {
        ("GET", "/api/materials"): httpx.Response(200, json=materials or []),
        ("GET", "/api/packaging-boxes"): httpx.Response(200, json=boxes or []),
        ("POST", "/api/packaging-boxes"): httpx.Response(
            201, json=created or BOX_CREATED
        ),
        ("PATCH", "/api/materials/bm9"): patch
        or httpx.Response(200, json={"id": "bm9", "name": BOX["name"]}),
    }


# ── dedup guards ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_box_article_refused_even_when_the_name_differs():
    """The article is the supplier's own key — it catches the case the name
    check cannot, one box spelled two ways across five years of invoices."""
    existing = {**MATERIAL, "id": "bm1", "name": "Коробка 120х100х80",
                "supplier_sku": "140"}
    mcp, client, seen = _build(_create_routes(materials=[existing]))
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool(
            "create_packaging_box",
            {**BOX_GEOMETRY, "name": "Коробка (120 x 100 x 80), бурая",
             "supplier_sku": "140"},
        )
    await client.aclose()

    assert "bm1" in str(exc.value)
    assert not [r for r in seen if r.url.path == "/api/packaging-boxes" and r.method == "POST"]


@pytest.mark.asyncio
async def test_duplicate_box_article_override_creates_it():
    mcp, client, seen = _build(
        _create_routes(materials=[{**MATERIAL, "supplier_sku": "140"}])
    )
    await mcp.call_tool(
        "create_packaging_box",
        {**BOX_GEOMETRY, "supplier_sku": "140", "allow_duplicate_sku": True,
         "allow_duplicate_name": True},
    )
    await client.aclose()
    assert [r for r in seen if (r.method, r.url.path) == ("POST", "/api/packaging-boxes")]


@pytest.mark.asyncio
async def test_duplicate_box_name_refused_from_the_materials_probe():
    """Post-WH-1 every box has a material of the same name, so the materials
    probe is the one that fires in practice."""
    existing = {**MATERIAL, "id": "bm1", "name": BOX["name"], "is_active": True}
    mcp, client, seen = _build(_create_routes(materials=[existing]))
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool("create_packaging_box", BOX_GEOMETRY)
    await client.aclose()

    assert "bm1" in str(exc.value)
    assert "allow_duplicate_name" in str(exc.value)
    assert not [r for r in seen if r.url.path == "/api/packaging-boxes" and r.method == "POST"]


@pytest.mark.asyncio
async def test_duplicate_box_name_refused_from_the_boxes_probe():
    """The belt to the materials braces: it only fires on a name desync that
    should be impossible, which is exactly why it is worth keeping."""
    mcp, client, seen = _build(_create_routes(boxes=[BOX]))
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool("create_packaging_box", BOX_GEOMETRY)
    await client.aclose()

    assert "b1" in str(exc.value)
    assert not [r for r in seen if r.url.path == "/api/packaging-boxes" and r.method == "POST"]


@pytest.mark.asyncio
async def test_name_clash_with_an_archived_box_says_it_is_archived():
    """Archived rows are probed, because a second pair hiding behind an archived
    namesake is invisible in every default listing. The message has to say the
    row is archived — nothing in the API or the UI can un-archive it, so
    "record a receipt against it instead" would be advice the agent cannot take.
    """
    archived = {**MATERIAL, "id": "bm1", "name": BOX["name"], "is_active": False}
    mcp, client, _ = _build(_create_routes(materials=[archived]))
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool("create_packaging_box", BOX_GEOMETRY)
    await client.aclose()

    assert "ARCHIVED" in str(exc.value)
    assert "un-archive" in str(exc.value)


@pytest.mark.asyncio
async def test_packaging_guard_refusals_are_not_logged():
    """Nothing was attempted and the owner already saw the refusal in the
    conversation — logging it would only add noise (module docstring)."""
    mcp, client, seen = _build(
        _create_routes(materials=[{**MATERIAL, "name": BOX["name"]}])
    )
    with pytest.raises(ToolError):
        await mcp.call_tool("create_packaging_box", BOX_GEOMETRY)
    await client.aclose()
    assert _logged(seen) == []


# ── composition ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_writes_geometry_then_the_material_fields():
    """One tool call, two requests, and the split has to be exact: the geometry
    schema is extra="forbid", so a supplier field sent there is a 422."""
    mcp, client, seen = _build(_create_routes())
    await mcp.call_tool(
        "create_packaging_box",
        {**BOX_GEOMETRY, "tare_weight_g": 42, "supplier_sku": "140",
         "supplier_name": "Упаковочки"},
    )
    await client.aclose()

    writes = [
        (r.method, r.url.path)
        for r in seen
        if r.method in ("POST", "PATCH")
        and r.url.path not in ("/api/agent-actions", "/api/auth/login")
    ]
    assert writes == [
        ("POST", "/api/packaging-boxes"),
        ("PATCH", "/api/materials/bm9"),
    ]

    posted = json.loads(next(
        r for r in seen if (r.method, r.url.path) == ("POST", "/api/packaging-boxes")
    ).content)
    assert posted["tare_weight_g"] == 42
    assert posted["low_stock_threshold"] == "5"  # rides the geometry request
    assert "supplier_sku" not in posted
    assert "supplier_name" not in posted

    patched = json.loads(next(
        r for r in seen if r.method == "PATCH"
    ).content)
    assert patched == {"supplier_sku": "140", "supplier_name": "Упаковочки"}


@pytest.mark.asyncio
async def test_create_without_supplier_fields_makes_only_one_write():
    mcp, client, seen = _build(_create_routes())
    await mcp.call_tool("create_packaging_box", BOX_GEOMETRY)
    await client.aclose()
    assert not [r for r in seen if r.method == "PATCH"]


@pytest.mark.asyncio
async def test_create_reports_the_material_id_to_book_receipts_against():
    """The box lands at zero stock and zero cost; the material id is the only
    way to give it either."""
    mcp, client, seen = _build(_create_routes())
    result = await mcp.call_tool("create_packaging_box", BOX_GEOMETRY)
    await client.aclose()

    assert "bm9" in json.dumps(result, default=str)
    entry = _logged(seen)[0]
    assert entry["object_type"] == "packaging_box"
    assert entry["object_id"] == "b9"
    assert "bm9" in entry["summary"]


@pytest.mark.asyncio
async def test_partial_create_names_both_ids_and_the_repair_call():
    """The geometry write has committed: the box exists, is valid and is usable.
    Raising would tell the agent the opposite and invite a second create, so the
    outcome is reported in the text instead."""
    mcp, client, seen = _build(
        _create_routes(patch=httpx.Response(500, json={"detail": "db is down"}))
    )
    result = await mcp.call_tool(
        "create_packaging_box", {**BOX_GEOMETRY, "supplier_sku": "140"}
    )
    await client.aclose()

    text = json.dumps(result, default=str, ensure_ascii=False)
    assert "PARTIAL" in text
    assert "b9" in text and "bm9" in text          # what was created
    assert "supplier_sku" in text                   # what was not set
    assert "db is down" in text                     # why
    assert "update_packaging_box" in text           # how to repair it

    # The half-applied pair is the kind of thing the owner needs to find later.
    failures = [e for e in _logged(seen) if not e["ok"]]
    assert len(failures) == 1
    assert failures[0]["object_id"] == "bm9"
    assert failures[0]["arguments"]["phase"] == "material_fields"


# ── update ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_rename_goes_to_the_packaging_endpoint():
    """Renaming from the material side is a 409 by design — catalog_service syncs
    the name the other way. The box surface is the only rename path."""
    routes = {
        ("GET", "/api/packaging-boxes"): httpx.Response(200, json=[BOX]),
        ("PATCH", "/api/packaging-boxes/b1"): httpx.Response(
            200, json={**BOX, "name": "Коробка бура 120×100×80"}
        ),
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "update_packaging_box",
        {"box_id": "b1", "name": "Коробка бура 120×100×80"},
    )
    await client.aclose()

    assert [r.url.path for r in seen if r.method == "PATCH"] == [
        "/api/packaging-boxes/b1"
    ]


@pytest.mark.asyncio
async def test_update_with_only_supplier_fields_patches_the_material():
    routes = {
        ("GET", "/api/packaging-boxes"): httpx.Response(200, json=[BOX]),
        ("PATCH", "/api/materials/bm1"): httpx.Response(200, json={"id": "bm1"}),
    }
    mcp, client, seen = _build(routes)
    await mcp.call_tool(
        "update_packaging_box", {"box_id": "b1", "supplier_sku": "140"}
    )
    await client.aclose()

    assert [r.url.path for r in seen if r.method == "PATCH"] == ["/api/materials/bm1"]


@pytest.mark.asyncio
async def test_update_unknown_box_refuses_before_writing_anything():
    mcp, client, seen = _build(
        {("GET", "/api/packaging-boxes"): httpx.Response(200, json=[BOX])}
    )
    with pytest.raises(ToolError, match="No packaging box"):
        await mcp.call_tool("update_packaging_box", {"box_id": "nope", "sort_order": 3})
    await client.aclose()
    assert not [r for r in seen if r.method == "PATCH"]


@pytest.mark.asyncio
async def test_empty_packaging_update_rejected():
    mcp, client, seen = _build({})
    with pytest.raises(ToolError, match="Nothing to update"):
        await mcp.call_tool("update_packaging_box", {"box_id": "b1"})
    await client.aclose()
    assert not [r for r in seen if r.method == "GET"]


@pytest.mark.asyncio
async def test_bad_packaging_type_rejected_before_any_request():
    mcp, client, seen = _build({})
    with pytest.raises(ToolError, match="ENVELOPE"):
        await mcp.call_tool(
            "create_packaging_box", {**BOX_GEOMETRY, "packaging_type": "TUBE"}
        )
    await client.aclose()
    assert not [r for r in seen if r.url.path != "/api/auth/login"]


# ── error translation ──────────────────────────────────────

@pytest.mark.asyncio
async def test_geometry_validation_error_names_the_field_and_the_constraint():
    """The backfill walks straight into max_weight_g > 0 and inner_height_mm > 0
    (an envelope has no height). The agent acts on this text, so the field and
    the rule have to be the readable part, not buried in a repr of FastAPI's
    error list."""
    routes = {
        ("GET", "/api/materials"): httpx.Response(200, json=[]),
        ("GET", "/api/packaging-boxes"): httpx.Response(200, json=[]),
        ("POST", "/api/packaging-boxes"): httpx.Response(
            422,
            json={"detail": [{
                "type": "greater_than",
                "loc": ["body", "max_weight_g"],
                "msg": "Input should be greater than 0",
                "input": 0,
                "ctx": {"gt": 0},
                "url": "https://errors.pydantic.dev/2.10/v/greater_than",
            }]},
        ),
    }
    mcp, client, _ = _build(routes)
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool("create_packaging_box", {**BOX_GEOMETRY, "max_weight_g": 0})
    await client.aclose()

    message = str(exc.value)
    assert "max_weight_g: Input should be greater than 0" in message
    assert "greater_than" not in message.split("max_weight_g")[0]  # no repr noise


@pytest.mark.asyncio
async def test_box_backed_rename_409_reaches_the_agent_readably():
    """update_material answers 409 for a box-backed rename. The agent has to
    understand it well enough to reach for update_packaging_box instead."""
    routes = {
        ("GET", "/api/materials"): httpx.Response(200, json=[]),
        ("PATCH", "/api/materials/bm1"): httpx.Response(
            409,
            json={"detail": "This material backs a packaging box; change its name "
                            "on the packaging page instead"},
        ),
    }
    mcp, client, seen = _build(routes)
    with pytest.raises(ToolError) as exc:
        await mcp.call_tool("update_material", {"material_id": "bm1", "name": "X"})
    await client.aclose()

    assert "packaging page instead" in str(exc.value)
    assert [e["ok"] for e in _logged(seen)] == [False]
