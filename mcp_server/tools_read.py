"""OrderHub MCP server — read tools (MCP-1).

Grounding surface: everything the agent needs to see before it writes anything.
Each tool is a 1:1 passthrough to an existing REST endpoint — no aggregation, no
reformatting, no rounding. Money values reach the agent exactly as the API
serialised them.

`list_packaging` (WH-4) is the single exception, and a narrow one: it merges two
passthroughs into one row. A box's geometry and its cost live on different
endpoints *by design* — `PackagingBoxRead` deliberately carries no cost field,
because its router is not cost-gated and the model is nested into ParcelEstimate
and OrderResponse (see the comment on that schema). Joining here rather than
there is what keeps the money behind `view_costs`. Still no arithmetic and no
rounding: every value is the string the API produced.

Tool docstrings are what the agent actually reads, so they carry the domain
rules it would otherwise have to guess (currency is locked at creation, BOMs are
product-level, receipts drive the weighted average).
"""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from client import OrderHubClient, OrderHubError


def dump(payload: Any) -> str:
    """Serialise an API response for the agent.

    `default=str` is a safety net for anything non-JSON-native; the API already
    returns plain JSON, so in practice this is a passthrough that preserves the
    exact numeric text the backend produced.
    """
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def register_read_tools(mcp: FastMCP, client: OrderHubClient) -> None:
    # ── shops ──────────────────────────────────────────────

    @mcp.tool()
    async def list_shops() -> str:
        """List the shops this agent can access.

        Only shops explicitly granted to the agent user are returned. Use this to
        resolve a shop_id before listing products or allocating an overhead
        expense to a shop.
        """
        return dump(await client.get("/api/shops"))

    # ── materials (direct materials — the COGS path) ───────

    @mcp.tool()
    async def list_materials(
        search: str | None = None,
        include_inactive: bool = False,
        category: str | None = None,
    ) -> str:
        """List direct materials — the leather, thread, hardware consumed by BOMs.

        Returns each material's `current_unit_cost` (a weighted average, in the
        material's own currency), `stock_quantity`, `unit`, `waste_percent` and
        `supplier_sku` (the supplier's article). Always check here for an
        existing material before creating a new one: near-duplicate rows
        fragment the weighted average and the stock ledger. Searching by the
        article from the invoice is the most reliable check — it is the
        supplier's own key, and survives the material being named differently.

        **Every packaging box is also a material** (WH-1), so unfiltered this
        returns the boxes' paired rows interleaved with the BOM materials. Pass
        `category="MATERIAL"` whenever you are working on recipes or checking
        for a duplicate before `create_material`; reach for `list_packaging`
        when you want boxes, since it joins the geometry on as well.

        **What `search` looks at:** the material name and `supplier_sku` — and
        nothing else. It does **not** match `supplier_name`, so searching for a
        supplier returns an empty list rather than that supplier's catalogue.
        Note also that box articles are short numerics (`140`, `165`, `058`), so
        an article lookup without `category="MATERIAL"` can turn up packaging.

        Args:
            search: case-insensitive substring match on the material name **or**
                its supplier article. Never on the supplier's name.
            include_inactive: include soft-deleted (discontinued) materials.
            category: `"MATERIAL"` for the direct materials a BOM consumes, or
                `"PACKAGING"` for the rows paired to packaging boxes. Omitted
                (the default) returns both.
        """
        return dump(
            await client.get(
                "/api/materials",
                search=search,
                include_inactive=include_inactive,
                category=category,
            )
        )

    @mcp.tool()
    async def get_material(material_id: str) -> str:
        """Fetch one direct material by id, including its current weighted-average
        unit cost, stock level, low-stock threshold and waste percent."""
        return dump(await client.get(f"/api/materials/{material_id}"))

    @mcp.tool()
    async def list_material_receipts(
        material_id: str, page: int = 1, limit: int = 20
    ) -> str:
        """List purchase receipts for a material, newest first.

        Each receipt is one purchase event and is what moves the material's
        weighted-average unit cost. `effective_unit_cost` folds in any shipping
        cost. Receipts are append-only — a mistake is corrected by a further
        receipt or a stock adjustment, never by deletion.
        """
        return dump(
            await client.get(
                f"/api/materials/{material_id}/receipts", page=page, limit=limit
            )
        )

    @mcp.tool()
    async def list_material_movements(
        material_id: str,
        reason: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> str:
        """List the append-only stock ledger for a material, newest first.

        Every change to `stock_quantity` has a row here. `delta` is signed, and
        `stock_quantity` on the material is the running sum.

        Args:
            reason: filter by one of `receipt`, `consumption`, `waste`,
                `adjustment`. `consumption` rows are written automatically when
                an order ships and carry the unit cost snapshot used for COGS.
        """
        return dump(
            await client.get(
                f"/api/materials/{material_id}/movements",
                reason=reason,
                page=page,
                limit=limit,
            )
        )

    @mcp.tool()
    async def list_receipts_by_invoice(invoice_no: str) -> str:
        """Show every line booked under one supplier invoice, in entry order.

        Use this to check a whole invoice at once instead of walking materials
        one at a time.

        Returns two blocks, because a real invoice mixes both kinds of line:
        `material_receipts` (direct materials, each with `material_name`, `qty`
        and `unit_cost`) and `overhead_receipts` (indirect lines such as a
        cutting service or a finishing compound, each with a flat `total_cost`).
        An invoice with no lines booked returns both blocks empty.

        There is no total — add the lines up yourself, and watch for lines in
        different currencies, which must not be summed together.

        Args:
            invoice_no: exactly as recorded on the receipts, e.g. "1996637412".
        """
        return dump(
            await client.get("/api/receipts/by-invoice", invoice_no=invoice_no)
        )

    # ── overhead materials (indirect — flat expenses) ──────

    @mcp.tool()
    async def list_overhead_materials(
        search: str | None = None, include_inactive: bool = False
    ) -> str:
        """List indirect/consumable materials — packaging tape, tools, studio
        supplies.

        Overhead materials carry no stock and no unit cost. They exist only so
        expenses can be booked against them. Anything a BOM consumes per finished
        unit belongs in `list_materials` instead, not here.
        """
        return dump(
            await client.get(
                "/api/overhead-materials",
                search=search,
                include_inactive=include_inactive,
            )
        )

    @mcp.tool()
    async def list_overhead_expenses(
        overhead_id: str, page: int = 1, limit: int = 20
    ) -> str:
        """List recorded expense events for an overhead material, newest first.

        Each row is a dated cost. `shop_id` may be null, meaning the expense is
        unallocated (global) rather than attributed to one shop.
        """
        return dump(
            await client.get(
                f"/api/overhead-materials/{overhead_id}/receipts",
                page=page,
                limit=limit,
            )
        )

    # ── packaging (WH-4) ───────────────────────────────────

    @mcp.tool()
    async def list_packaging(include_archived: bool = False) -> str:
        """List packaging boxes with their paired material — geometry and money
        in one view.

        Every box **is** a material (WH-1). The box row carries the geometry the
        parcel calculator fits products into; the material carries stock,
        weighted-average unit cost, the supplier article and the archive state.
        Each row here joins the two and includes `material_id`.

        **Stock and cost are not changed here, or by any packaging tool.** Use
        `material_id` with the materials tools: `record_material_receipt` to book
        a purchase of boxes (this is what sets their unit cost),
        `adjust_material_stock` for a stocktake correction,
        `list_material_receipts` / `list_material_movements` for the history.

        Dimensions are **inner** millimetres — the usable space inside the box.
        `tare_weight_g` is the weight of the empty box; `max_weight_g` is what it
        may carry. The two are easy to confuse on a supplier's card.

        Args:
            include_archived: include boxes whose material has been deactivated.
                Default false. An archived box drops out of the packaging picker
                and the parcel calculator but keeps its receipts and its ledger.
        """
        boxes = await client.get(
            "/api/packaging-boxes", include_archived=include_archived
        )

        # Archived materials are always fetched: which boxes are shown is decided
        # by the geometry endpoint above, and a row it returned must never lose
        # its cost half here.
        try:
            materials = await client.get(
                "/api/materials", category="PACKAGING", include_inactive=True
            )
        except OrderHubError as exc:
            return (
                f"WARNING: the paired materials could not be read ({exc}). The "
                "geometry below is complete; stock, unit cost and supplier "
                "article are missing from every row.\n" + dump(boxes)
            )

        by_id = {m["id"]: m for m in materials}
        rows = []
        for box in boxes:
            material = by_id.get(box["material_id"], {})
            rows.append(
                {
                    **box,
                    "current_unit_cost": material.get("current_unit_cost"),
                    "currency": material.get("currency"),
                    "supplier_sku": material.get("supplier_sku"),
                    "supplier_name": material.get("supplier_name"),
                }
            )
        return dump(rows)

    # ── catalog + BOM ──────────────────────────────────────

    @mcp.tool()
    async def list_products(shop_id: str, is_active: bool = True) -> str:
        """List a shop's products with their variants.

        A BOM (recipe) attaches to the **product**, not to individual variants —
        so use the product id from here when reading or writing a recipe.

        `default_packaging_box_id` is the box this product normally ships in (WH-5),
        or null. It is a bare id — `list_packaging` maps ids to names. Set it with
        `set_default_packaging`, never through a recipe line: a box is one per
        parcel, not one per product.
        """
        return dump(
            await client.get(f"/api/shops/{shop_id}/products", is_active=is_active)
        )

    @mcp.tool()
    async def get_product(product_id: str) -> str:
        """Fetch one product with its variants (SKU, dimensions, price, stock).

        Also carries `default_packaging_box_id` — see `list_products`.
        """
        return dump(await client.get(f"/api/products/{product_id}"))

    @mcp.tool()
    async def get_product_bom(product_id: str) -> str:
        """Fetch a product's recipe (BOM) plus a per-currency cost preview.

        Returns one line per material with `qty_per_unit` and `line_cost`, and
        `has_inactive_material` if any line points at a discontinued material.

        **Always call this before changing a recipe.** The underlying write is a
        full replacement, so a partial payload silently deletes the lines it
        omits.
        """
        return dump(await client.get(f"/api/products/{product_id}/bom"))

    @mcp.tool()
    async def compute_product_cost(
        product_id: str, in_currency: str | None = None
    ) -> str:
        """Recompute a product's theoretical unit cost from its recipe, live.

        Returns `basis`: the summed
        `qty_per_unit * (1 + waste_percent/100) * material.current_unit_cost`,
        grouped by material currency. Use this to check a recipe's cost after
        editing it, or to answer "what does this product cost to make right now".

        Pass `in_currency` (e.g. "USD") to also get `converted`: the whole recipe
        in that currency at the current UAH/USD rate, with the rate that produced
        it. Materials are priced in UAH, so this is what a USD shop's order will
        actually book. `converted` is null if no rate is configured or the
        currency is anything other than UAH/USD — the `basis` is still correct.

        Note: this is the *theoretical* cost from current material prices and
        today's rate. The cost booked against an order is snapshotted when that
        order ships, at the prices and rate in force then, not today's.
        """
        # `in` is a Python keyword, so it cannot be written as a kwarg literal.
        params = {"in": in_currency} if in_currency else {}
        return dump(await client.get(f"/api/products/{product_id}/bom/cost", **params))

    # ── delivery tracking (WB-TRACK-1) ─────────────────────

    @mcp.tool()
    async def check_parcel_delivery(state: str | None = None) -> str:
        """Delivery status of the WesternBid parcels currently in flight.

        Answers "what has arrived, what is still moving, what is stuck" from Nova
        Poshta's own tracking, which WesternBid itself cannot provide — WB's
        status only covers its leg to the Lviv warehouse and stops exactly where
        delivery begins.

        `counts` always describes the full set even when `state` filters the
        rows. Each parcel carries a `state` plus two INDEPENDENT attention flags;
        a parcel can be flagged by either or both:

          * `is_overdue` — Nova Poshta's own `scheduled_delivery_at` has passed
            and the parcel is not delivered. Their commitment, not our estimate.
            `days_overdue` says by how much; report the worst first.
          * `is_stalled` — no carrier scan for `stalled_days` days. This catches
            a parcel sitting in a warehouse inside a generous delivery window,
            which `is_overdue` alone would miss.

        States:
          * `delivered` — arrived; `delivered_at` is when the recipient got it.
          * `moving`    — in transit, nothing wrong.
          * `problem`   — Nova Poshta reports a failed delivery attempt, refusal,
            return or storage expiry. Needs a human, not a wait.
          * `no_data`   — Nova Poshta has stopped returning data for a number
            that previously worked. Say exactly that; do NOT tell the owner the
            parcel was deleted, canceled or reassigned — NP documents no reason
            and we do not know which it is. `status_text` still holds the last
            status we saw, and `no_data_since` when it went quiet.
          * `untracked` — a UPS or USPS parcel. Nova Poshta cannot track these
            and this sprint does not either. Never omit them from an answer:
            report them and say they must be checked by hand.

        `status_text` is Nova Poshta's own Ukrainian wording, verbatim. Quote it
        rather than paraphrasing — it names the city the parcel is in.

        `polled_at` is when the daily job last ran. If it is null or old, say so
        before reporting anything as "still moving": nothing has been refreshed.

        Args:
            state: optionally filter to one of the states above.
        """
        return dump(await client.get("/api/westernbid/tracking", state=state))
