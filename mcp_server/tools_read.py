"""OrderHub MCP server — read tools (MCP-1).

Grounding surface: everything the agent needs to see before it writes anything.
Each tool is a 1:1 passthrough to an existing REST endpoint — no aggregation, no
reformatting, no rounding. Money values reach the agent exactly as the API
serialised them.

Tool docstrings are what the agent actually reads, so they carry the domain
rules it would otherwise have to guess (currency is locked at creation, BOMs are
product-level, receipts drive the weighted average).
"""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from client import OrderHubClient


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
        search: str | None = None, include_inactive: bool = False
    ) -> str:
        """List direct materials — the leather, thread, hardware consumed by BOMs.

        Returns each material's `current_unit_cost` (a weighted average, in the
        material's own currency), `stock_quantity`, `unit`, and `waste_percent`.
        Always check here for an existing material before creating a new one:
        near-duplicate rows fragment the weighted average and the stock ledger.

        Args:
            search: case-insensitive substring match on the material name.
            include_inactive: include soft-deleted (discontinued) materials.
        """
        return dump(
            await client.get(
                "/api/materials", search=search, include_inactive=include_inactive
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

    # ── catalog + BOM ──────────────────────────────────────

    @mcp.tool()
    async def list_products(shop_id: str, is_active: bool = True) -> str:
        """List a shop's products with their variants.

        A BOM (recipe) attaches to the **product**, not to individual variants —
        so use the product id from here when reading or writing a recipe.
        """
        return dump(
            await client.get(f"/api/shops/{shop_id}/products", is_active=is_active)
        )

    @mcp.tool()
    async def get_product(product_id: str) -> str:
        """Fetch one product with its variants (SKU, dimensions, price, stock)."""
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
    async def compute_product_cost(product_id: str) -> str:
        """Recompute a product's theoretical unit cost from its recipe, live.

        Returns the summed `qty_per_unit * material.current_unit_cost` grouped by
        material currency. Use this to check a recipe's cost after editing it, or
        to answer "what does this product cost to make right now".

        Note: this is the *theoretical* cost from current material prices. The
        cost actually booked against an order is snapshotted when that order
        ships, so it reflects material prices at ship time, not today's.
        """
        return dump(await client.get(f"/api/products/{product_id}/bom/cost"))
