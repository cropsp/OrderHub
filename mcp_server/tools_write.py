"""OrderHub MCP server — write tools (MCP-2).

Every tool is a passthrough to an existing REST endpoint, so the router's own
guards, validation and transaction boundaries apply unchanged (§5.4). Three
things are layered on top, and only three:

1. **Action logging (§5.8).** Each write reports itself to
   /api/agent-actions — tool, arguments, outcome. The domain tables record what
   changed; this records what the agent *meant*, which is the part that would
   otherwise be lost. Attempts that reached the API and were *rejected* are
   logged too (ok=false), because a repeated 403 or validation failure is signal.
   Attempts stopped by the guards below are deliberately NOT logged: nothing was
   attempted, and the refusal is already visible to the owner in the
   conversation, so logging it would only add noise to the normal
   refuse-then-confirm flow.
2. **BOM wipe protection (§5.5).** `PUT /bom` is delete-all + reinsert with no
   audit and no undo, so `set_product_bom` refuses a destructive replacement
   unless it is confirmed, and `add_bom_line` / `remove_bom_line` exist so the
   agent never has to send a full replacement to make a small change.
3. **Duplicate-material guard.** Creating a second "Шкіра чорна" fragments the
   weighted average across two rows permanently. An exact collision on the
   supplier's article (MAT-6) or on the name is refused with the existing id,
   each overridable in one argument. The article is checked first and reported
   even when the name differs: it is the supplier's own key, so it catches the
   case the name check cannot — one material spelled two ways across invoices.

Quantities and money are passed as decimal *strings* ("5.00", "597.14") end to
end. Binary floats do not round-trip cents, and these values land in Numeric
columns.
"""

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from client import OrderHubClient, OrderHubError
from tools_read import dump


class BomLine(BaseModel):
    """One recipe line."""

    material_id: str
    qty_per_unit: str = Field(
        ..., description="Decimal string, e.g. '5.00' — amount per finished unit."
    )
    notes: str | None = None


# ── action log ─────────────────────────────────────────────

async def _report(
    client: OrderHubClient,
    tool: str,
    arguments: dict[str, Any],
    *,
    ok: bool,
    object_type: str | None = None,
    object_id: str | None = None,
    summary: str | None = None,
    error: str | None = None,
) -> str | None:
    """Record one action. Returns a warning string if the log itself failed.

    Never raises: the write it describes has already happened, so failing here
    would misreport a successful mutation as a failure. The warning is surfaced
    in the tool's output instead, so a silently broken audit trail is visible
    rather than assumed.
    """
    try:
        await client.post(
            "/api/agent-actions",
            {
                "tool": tool,
                "arguments": arguments,
                "ok": ok,
                "object_type": object_type,
                "object_id": object_id,
                "summary": summary,
                "error": error,
            },
        )
        return None
    except (OrderHubError, Exception) as exc:  # noqa: BLE001 - deliberately broad
        return f"WARNING: action log write failed ({exc}). The change itself succeeded."


async def _logged(
    client: OrderHubClient,
    tool: str,
    arguments: dict[str, Any],
    object_type: str,
    call: Callable,
    *,
    summarise: Callable[[Any], str] | None = None,
    object_id: Callable[[Any], str | None] | None = None,
) -> str:
    """Run one write, record it, and render the result for the agent."""
    try:
        result = await call()
    except OrderHubError as exc:
        await _report(
            client, tool, arguments, ok=False, object_type=object_type, error=str(exc)
        )
        raise

    summary = summarise(result) if summarise else None
    warning = await _report(
        client,
        tool,
        arguments,
        ok=True,
        object_type=object_type,
        object_id=object_id(result) if object_id else _id_of(result),
        summary=summary,
    )

    rendered = dump(result)
    parts = [p for p in (summary, warning, rendered) if p]
    return "\n".join(parts)


def _id_of(result: Any) -> str | None:
    return result.get("id") if isinstance(result, dict) else None


def _dec(value: str, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ToolError(f"{field} must be a decimal number, got {value!r}")


# ── packaging pairing (WH-4) ───────────────────────────────
#
# A packaging box is a geometry row plus a Material, created together and kept in
# step by catalog_service. Three of the material's fields have no home on the
# geometry schema (which is extra="forbid", so sending them there is a 422), and
# the packaging surface is the only place a box may be named. So the box tools
# compose two requests: the geometry endpoint, then the material one.
#
# `low_stock_threshold` is deliberately NOT one of them: PackagingBoxCreate and
# PackagingBoxUpdate already carry it and catalog_service writes it onto the
# material, so it rides the geometry request like any other box field.


def _present(**fields: Any) -> dict[str, Any]:
    """Drop unset (None) arguments so a PATCH touches only what was named."""
    return {k: v for k, v in fields.items() if v is not None}


def _material_side(
    supplier_sku: str | None, supplier_name: str | None, notes: str | None
) -> dict[str, Any]:
    """The fields a box carries on its material rather than on its geometry.

    One definition for both tools: the split has to be identical on create and on
    update, or a field would land on the wrong endpoint on one of the two paths.
    """
    return _present(
        supplier_sku=supplier_sku, supplier_name=supplier_name, notes=notes
    )


def _name_clash(rows: list[dict], name: str) -> dict | None:
    """First row whose name matches `name` exactly, ignoring case and padding."""
    target = name.strip().lower()
    return next((r for r in rows if (r.get("name") or "").strip().lower() == target), None)


async def _apply_material_side(
    client: OrderHubClient,
    tool: str,
    box_id: str,
    material_id: str,
    patch: dict[str, Any],
    box_result: str,
) -> str:
    """Set the paired material's supplier fields, reporting a failure loudly.

    The geometry write has already committed by the time this runs, so a failure
    here is a PARTIAL, not a failure: the box exists, is valid and is usable —
    it is just missing its article. Raising would tell the agent the opposite and
    invite it to create the box a second time, so the outcome is reported in the
    returned text instead, naming both ids and the exact repair call. Same shape
    as the action-log warning in `_report`: the write happened, something
    adjacent did not.

    The failed attempt IS written to the action log, because a half-configured
    pair is precisely the kind of thing the owner needs to find later.
    """
    if not patch:
        return box_result

    try:
        await client.patch(f"/api/materials/{material_id}", patch)
    except OrderHubError as exc:
        await _report(
            client,
            tool,
            {"box_id": box_id, "material_id": material_id, "phase": "material_fields", **patch},
            ok=False,
            object_type="material",
            object_id=material_id,
            error=str(exc),
        )
        unset = ", ".join(f"{k}={v!r}" for k, v in patch.items())
        fix = ", ".join(f'{k}="{v}"' for k, v in patch.items())
        return (
            "PARTIAL — the box was written, the supplier fields were not.\n\n"
            f"  box_id:      {box_id}\n"
            f"  material_id: {material_id}\n"
            f"  NOT set:     {unset}\n"
            f"  reason:      {exc}\n\n"
            "Do NOT create the box again. Set the fields with:\n"
            f'  update_packaging_box(box_id="{box_id}", {fix})\n\n'
            f"{box_result}"
        )

    return box_result


# ── BOM diffing (§5.5) ─────────────────────────────────────

def _bom_index(items: list[dict]) -> dict[str, dict]:
    return {item["material_id"]: item for item in items}


def _diff_bom(old: list[dict], new: list[BomLine]) -> dict[str, list[str]]:
    """Compare a current recipe against a proposed one, keyed by material."""
    old_by_id = _bom_index(old)
    new_by_id = {line.material_id: line for line in new}
    names = {item["material_id"]: item["material_name"] for item in old}

    removed = [
        f"{names.get(mid, mid)} ({old_by_id[mid]['qty_per_unit']})"
        for mid in old_by_id
        if mid not in new_by_id
    ]
    added = [
        f"{line.material_id} ({line.qty_per_unit})"
        for mid, line in new_by_id.items()
        if mid not in old_by_id
    ]
    changed = [
        f"{names.get(mid, mid)}: {old_by_id[mid]['qty_per_unit']} -> {line.qty_per_unit}"
        for mid, line in new_by_id.items()
        if mid in old_by_id
        and _dec(line.qty_per_unit, "qty_per_unit")
        != _dec(old_by_id[mid]["qty_per_unit"], "qty_per_unit")
    ]
    return {"added": added, "removed": removed, "changed": changed}


def _render_diff(diff: dict[str, list[str]]) -> str:
    lines = []
    for label, key in (("Removed", "removed"), ("Added", "added"), ("Changed", "changed")):
        for entry in diff[key]:
            lines.append(f"  {label}: {entry}")
    return "\n".join(lines) if lines else "  (no change)"


def register_write_tools(mcp: FastMCP, client: OrderHubClient) -> None:
    # ── materials ──────────────────────────────────────────

    @mcp.tool()
    async def create_material(
        name: str,
        unit: str,
        currency: str,
        supplier_name: str | None = None,
        supplier_sku: str | None = None,
        notes: str | None = None,
        allow_duplicate_name: bool = False,
        allow_duplicate_sku: bool = False,
    ) -> str:
        """Create a direct material.

        The material starts with zero stock and zero unit cost — record a receipt
        to give it both. **Currency is locked at creation and cannot be changed
        afterwards**; every receipt for this material must match it.

        Two duplicate guards, because two rows for one real material split the
        weighted average permanently:

        - an active material with this exact `supplier_sku` — the stronger signal,
          checked first, and reported **even if the name differs**, since that is
          exactly the "same material spelled differently on two invoices" case;
        - an active material with this exact name.

        Search first with `list_materials` (which matches the article as well as
        the name). Pass the matching override only when the collision really is
        two different things.

        Args:
            name: e.g. "Шкіра італійська чорна".
            unit: the unit purchases and recipes are measured in — "dm2", "m2",
                "pcs", "m". Pick the unit the supplier invoices in.
            currency: ISO 4217, e.g. "UAH".
            supplier_sku: the supplier's article (артикул) from the invoice, e.g.
                "027515". This is what ties one material across invoices — always
                set it when the invoice shows one.
        """
        args = {
            "name": name, "unit": unit, "currency": currency,
            "supplier_sku": supplier_sku,
        }

        if supplier_sku and not allow_duplicate_sku:
            by_sku = await client.get("/api/materials", search=supplier_sku)
            clash = [
                m
                for m in by_sku
                if (m.get("supplier_sku") or "").strip().lower()
                == supplier_sku.strip().lower()
            ]
            if clash:
                raise ToolError(
                    f"Article {supplier_sku!r} already belongs to "
                    f"{clash[0]['name']!r} (id {clash[0]['id']}, "
                    f"{clash[0]['current_unit_cost']} {clash[0]['currency']}/"
                    f"{clash[0]['unit']}). The article is the supplier's own key, "
                    "so this is very likely the same material under a different "
                    "name — record a receipt against it instead of creating a "
                    "second row. Pass allow_duplicate_sku=True only if the "
                    "supplier genuinely reuses this code for a different item."
                )

        if not allow_duplicate_name:
            existing = await client.get("/api/materials", search=name)
            clash = [m for m in existing if m["name"].strip().lower() == name.strip().lower()]
            if clash:
                raise ToolError(
                    f"A material named {name!r} already exists (id {clash[0]['id']}, "
                    f"{clash[0]['current_unit_cost']} {clash[0]['currency']}/"
                    f"{clash[0]['unit']}). Record a receipt against it instead of "
                    "creating a second row, or pass allow_duplicate_name=True if "
                    "these really are different materials."
                )

        return await _logged(
            client, "create_material", args, "material",
            lambda: client.post(
                "/api/materials",
                {
                    "name": name,
                    "unit": unit,
                    "currency": currency,
                    "supplier_name": supplier_name,
                    "supplier_sku": supplier_sku,
                    "notes": notes,
                },
            ),
            summarise=lambda r: f"Created material {r['name']} ({r['unit']}, {r['currency']}).",
        )

    @mcp.tool()
    async def update_material(
        material_id: str,
        name: str | None = None,
        unit: str | None = None,
        supplier_name: str | None = None,
        supplier_sku: str | None = None,
        notes: str | None = None,
        low_stock_threshold: str | None = None,
        waste_percent: str | None = None,
    ) -> str:
        """Update a material's descriptive fields and stock policy.

        Currency, unit cost and stock quantity are deliberately not editable
        here: cost moves only through receipts, and stock only through receipts
        or adjustments, so the ledger always explains the numbers.

        Args:
            supplier_sku: the supplier's article (артикул), e.g. "027515". Set it
                on an older material that predates the field — it is what lets a
                later invoice match this row instead of creating a duplicate.
            low_stock_threshold: decimal string; the material is flagged when
                stock falls to or below it.
            waste_percent: decimal string 0-100; extra material consumed per unit
                to account for offcuts. Applied automatically when an order ships.
        """
        patch = {
            k: v
            for k, v in {
                "name": name,
                "unit": unit,
                "supplier_name": supplier_name,
                "supplier_sku": supplier_sku,
                "notes": notes,
                "low_stock_threshold": low_stock_threshold,
                "waste_percent": waste_percent,
            }.items()
            if v is not None
        }
        if not patch:
            raise ToolError("Nothing to update — pass at least one field.")

        return await _logged(
            client, "update_material", {"material_id": material_id, **patch}, "material",
            lambda: client.patch(f"/api/materials/{material_id}", patch),
            summarise=lambda r: f"Updated {r['name']}: {', '.join(patch)}.",
            object_id=lambda r: material_id,
        )

    @mcp.tool()
    async def archive_material(material_id: str) -> str:
        """Discontinue a material (soft delete — history is preserved).

        It disappears from the default catalog listing and cannot be added to new
        recipes, but existing recipes that already reference it keep working and
        its receipts and ledger stay intact.
        """
        return await _logged(
            client, "archive_material", {"material_id": material_id}, "material",
            lambda: client.delete(f"/api/materials/{material_id}"),
            summarise=lambda r: f"Archived material {material_id}.",
            object_id=lambda r: material_id,
        )

    # ── packaging (WH-4) ───────────────────────────────────

    async def _find_box(box_id: str) -> dict:
        """Resolve one box, archived or not. There is no GET by id on this router."""
        boxes = await client.get("/api/packaging-boxes", include_archived=True)
        box = next((b for b in boxes if str(b["id"]) == str(box_id)), None)
        if box is None:
            raise ToolError(
                f"No packaging box with id {box_id}. Call list_packaging "
                "(include_archived=True to see archived ones) for the current ids."
            )
        return box

    @mcp.tool()
    async def create_packaging_box(
        name: str,
        inner_length_mm: int,
        inner_width_mm: int,
        inner_height_mm: int,
        max_weight_g: int,
        packaging_type: str = "BOX",
        max_thickness_mm: int | None = None,
        tare_weight_g: int = 0,
        sort_order: int = 0,
        low_stock_threshold: str = "5",
        supplier_sku: str | None = None,
        supplier_name: str | None = None,
        notes: str | None = None,
        allow_duplicate_sku: bool = False,
        allow_duplicate_name: bool = False,
    ) -> str:
        """Create a packaging box — the geometry row **and** its paired material.

        A box is a material with a shape (WH-1), and this makes both in one call:
        the geometry the parcel calculator fits products into, and the material
        that carries stock, weighted-average cost, the supplier article and the
        archive flag. The `material_id` comes back in the result.

        The new box starts at **zero stock and zero cost**. Give it both by
        calling `record_material_receipt` against that `material_id` — there is
        deliberately no way to hand a box units with no price behind them.

        All dimensions are **inner** millimetres: the usable space inside, not
        the outside of the carton. Suppliers usually publish inner dims, but a
        size lifted from a product name may be either — check before trusting it.

        Two duplicate guards, the same pair as `create_material`, so re-running a
        catalog import is safe: an existing material with this exact
        `supplier_sku` (checked first, and reported even when the name differs —
        it is the supplier's own key), then an existing box or material with this
        exact name, archived ones included. Call `list_packaging` first.

        Args:
            name: as the supplier lists it, e.g. "Коробка (120 x 100 x 80),
                бурая". Max 100 characters.
            packaging_type: "BOX" or "ENVELOPE".
            inner_length_mm: inner length, must be > 0.
            inner_width_mm: inner width, must be > 0.
            inner_height_mm: inner height, must be > 0 — **including for an
                ENVELOPE**, which has no real height. Give the flat thickness
                (1 if it is genuinely flat) and put the true limit in
                `max_thickness_mm`.
            max_weight_g: what the box may **carry**. Required, must be > 0, and
                is NOT the weight of the box itself. Suppliers rarely publish a
                load limit; 5000 is the agreed default when it is unknown, to be
                corrected later on the boxes that matter.
            tare_weight_g: the weight of the **empty** box. Defaults to 0, which
                makes the parcel calculator estimate parcels lighter than they
                are — set it whenever the supplier's card gives it.
            low_stock_threshold: decimal string. Stored on the paired material;
                the box is flagged when stock falls to or below it.
            supplier_sku: the supplier's article (артикул). Always set it when
                the invoice or product card shows one — it is what ties this box
                to a later purchase instead of spawning a second row.
        """
        if packaging_type not in ("BOX", "ENVELOPE"):
            raise ToolError(
                f"packaging_type must be 'BOX' or 'ENVELOPE', got {packaging_type!r}"
            )
        _dec(low_stock_threshold, "low_stock_threshold")

        if supplier_sku and not allow_duplicate_sku:
            by_sku = await client.get("/api/materials", search=supplier_sku)
            clash = [
                m
                for m in by_sku
                if (m.get("supplier_sku") or "").strip().lower()
                == supplier_sku.strip().lower()
            ]
            if clash:
                raise ToolError(
                    f"Article {supplier_sku!r} already belongs to "
                    f"{clash[0]['name']!r} (material id {clash[0]['id']}). The "
                    "article is the supplier's own key, so this is very likely "
                    "the same box under a different name — record a receipt "
                    "against it instead of creating a second one. Pass "
                    "allow_duplicate_sku=True only if the supplier genuinely "
                    "reuses this code for a different item."
                )

        if not allow_duplicate_name:
            # Archived rows are probed too. A second pair created behind an
            # archived namesake is exactly the drift this guard exists to stop,
            # and it would be invisible in the default listing.
            #
            # Both probes run because rule 3 names both surfaces. In practice the
            # materials one subsumes the boxes one — the pair is 1:1 and both
            # rename paths sync or refuse — so the second only fires on a desync
            # that should be impossible, which is a reason to keep it.
            by_name = await client.get(
                "/api/materials", search=name, include_inactive=True
            )
            clash, kind = _name_clash(by_name, name), "material"
            archived = clash is not None and not clash.get("is_active", True)
            if clash is None:
                boxes = await client.get("/api/packaging-boxes", include_archived=True)
                clash, kind = _name_clash(boxes, name), "box"
                archived = clash is not None and not clash.get("material_is_active", True)

            if clash is not None:
                remedy = (
                    "it is ARCHIVED. Nothing in the API or the UI can un-archive "
                    "it, so bringing it back is a database job for the owner."
                    if archived
                    else "Record a receipt against it instead of creating a second one."
                )
                raise ToolError(
                    f"A {kind} named {name!r} already exists (id {clash['id']}) — "
                    f"{remedy} Pass allow_duplicate_name=True if these really are "
                    "two different things."
                )

        payload = {
            "name": name,
            "packaging_type": packaging_type,
            "inner_length_mm": inner_length_mm,
            "inner_width_mm": inner_width_mm,
            "inner_height_mm": inner_height_mm,
            "max_thickness_mm": max_thickness_mm,
            "max_weight_g": max_weight_g,
            "tare_weight_g": tare_weight_g,
            "sort_order": sort_order,
            "low_stock_threshold": low_stock_threshold,
        }
        material_patch = _material_side(supplier_sku, supplier_name, notes)
        args = {**payload, **material_patch}

        # PackagingBoxCreate is extra="forbid", so the material-side fields must
        # not ride this payload — they are a second request.
        created: list[dict] = []

        async def _create():
            result = await client.post("/api/packaging-boxes", payload)
            created.append(result)
            return result

        box_result = await _logged(
            client, "create_packaging_box", args, "packaging_box", _create,
            summarise=lambda r: (
                f"Created packaging box {r['name']} ({r['packaging_type']}, "
                f"{r['inner_length_mm']}×{r['inner_width_mm']}×{r['inner_height_mm']}mm "
                f"inner, max {r['max_weight_g']}g). Material {r['material_id']} — "
                "book a receipt against it to give the box stock and a unit cost."
            ),
        )

        box = created[0]
        return await _apply_material_side(
            client, "create_packaging_box", str(box["id"]),
            str(box["material_id"]), material_patch, box_result,
        )

    @mcp.tool()
    async def update_packaging_box(
        box_id: str,
        name: str | None = None,
        packaging_type: str | None = None,
        inner_length_mm: int | None = None,
        inner_width_mm: int | None = None,
        inner_height_mm: int | None = None,
        max_thickness_mm: int | None = None,
        max_weight_g: int | None = None,
        tare_weight_g: int | None = None,
        sort_order: int | None = None,
        low_stock_threshold: str | None = None,
        supplier_sku: str | None = None,
        supplier_name: str | None = None,
        notes: str | None = None,
    ) -> str:
        """Update a packaging box — geometry, name, or its material's supplier
        fields. Omitted fields are left alone.

        **This is where a box is renamed.** The rename syncs onto the paired
        material automatically. Renaming it from the material side is refused
        with a 409 ("This material backs a packaging box; change its name on the
        packaging page instead"), because a rename there would desync the pair
        with nothing to detect the drift — so never reach for `update_material`
        on a box-backed material, for its name or its category. Its supplier
        article, supplier name and notes are fine to set from either side; this
        tool sets them for you.

        **Stock and cost are not touched here and cannot be.** Use
        `record_material_receipt` or `adjust_material_stock` against the box's
        `material_id`, which `list_packaging` returns.

        Every dimension is **inner** millimetres and must be > 0 if given, as
        must `max_weight_g` — which is the load the box may carry, not the weight
        of the box (that is `tare_weight_g`).
        """
        if packaging_type is not None and packaging_type not in ("BOX", "ENVELOPE"):
            raise ToolError(
                f"packaging_type must be 'BOX' or 'ENVELOPE', got {packaging_type!r}"
            )
        if low_stock_threshold is not None:
            _dec(low_stock_threshold, "low_stock_threshold")

        geometry = _present(
            name=name,
            packaging_type=packaging_type,
            inner_length_mm=inner_length_mm,
            inner_width_mm=inner_width_mm,
            inner_height_mm=inner_height_mm,
            max_thickness_mm=max_thickness_mm,
            max_weight_g=max_weight_g,
            tare_weight_g=tare_weight_g,
            sort_order=sort_order,
            low_stock_threshold=low_stock_threshold,
        )
        material_patch = _material_side(supplier_sku, supplier_name, notes)
        if not geometry and not material_patch:
            raise ToolError("Nothing to update — pass at least one field.")

        box = await _find_box(box_id)
        material_id = str(box["material_id"])
        args = {"box_id": box_id, **geometry, **material_patch}

        if geometry:
            box_result = await _logged(
                client, "update_packaging_box", args, "packaging_box",
                lambda: client.patch(f"/api/packaging-boxes/{box_id}", geometry),
                summarise=lambda r: (
                    f"Updated {box['name']}"
                    + (f" -> {r['name']}" if "name" in geometry else "")
                    + f": {', '.join(geometry)}."
                ),
                object_id=lambda r: box_id,
            )
        else:
            # Nothing to change on the geometry row — the material patch below is
            # the whole write, and reports itself.
            box_result = await _logged(
                client, "update_packaging_box", args, "packaging_box",
                lambda: client.patch(f"/api/materials/{material_id}", material_patch),
                summarise=lambda r: (
                    f"Updated {box['name']}: {', '.join(material_patch)}."
                ),
                object_id=lambda r: box_id,
            )
            return box_result

        return await _apply_material_side(
            client, "update_packaging_box", box_id, material_id,
            material_patch, box_result,
        )

    # ── receipts + stock ───────────────────────────────────

    @mcp.tool()
    async def record_material_receipt(
        material_id: str,
        qty: str,
        unit_cost: str,
        currency: str,
        shipping_cost: str | None = None,
        supplier: str | None = None,
        invoice_no: str | None = None,
        received_at: str | None = None,
        notes: str | None = None,
    ) -> str:
        """Record a purchase of a material. This is what sets its cost.

        Adds `qty` to stock and recomputes the weighted-average unit cost:
        old stock and old cost are blended with this purchase. `shipping_cost` is
        spread across the quantity, so a delivery charge raises the effective unit
        cost correctly.

        **Append-only.** A receipt cannot be edited or deleted — a mistake is
        corrected by another receipt or a stock adjustment, and both stay in the
        ledger. Confirm the numbers before calling.

        Args:
            qty: decimal string, must be > 0, in the material's unit.
            unit_cost: decimal string, price per unit excluding shipping.
            currency: must equal the material's currency, or the call is rejected.
            received_at: ISO 8601 timestamp. Defaults to now — set it when
                back-entering an older invoice, since the P&L dates costs by this.
        """
        _dec(qty, "qty")
        _dec(unit_cost, "unit_cost")
        before = await client.get(f"/api/materials/{material_id}")

        args = {
            "material_id": material_id, "qty": qty, "unit_cost": unit_cost,
            "currency": currency, "shipping_cost": shipping_cost,
            "supplier": supplier, "invoice_no": invoice_no,
            "received_at": received_at,
        }

        def summarise(result):
            after = result["material"]
            return (
                f"{before['name']}: +{qty} {after['unit']} @ {unit_cost} {currency}"
                f"{f' (+{shipping_cost} shipping)' if shipping_cost else ''}. "
                f"Unit cost {before['current_unit_cost']} -> {after['current_unit_cost']}; "
                f"stock {before['stock_quantity']} -> {after['stock_quantity']}."
            )

        return await _logged(
            client, "record_material_receipt", args, "material_receipt",
            lambda: client.post(
                f"/api/materials/{material_id}/receipts",
                {
                    "qty": qty, "unit_cost": unit_cost, "currency": currency,
                    "shipping_cost": shipping_cost, "supplier": supplier,
                    "invoice_no": invoice_no, "received_at": received_at,
                    "notes": notes,
                },
            ),
            summarise=summarise,
            object_id=lambda r: r["receipt"]["id"],
        )

    @mcp.tool()
    async def adjust_material_stock(
        material_id: str, delta: str, reason: str, notes: str | None = None
    ) -> str:
        """Correct a material's stock level without recording a purchase.

        Use this for a stocktake correction or for material lost or spoiled. It
        moves stock only — the unit cost is untouched, because no money changed
        hands. Stock is allowed to go negative; that is a signal to restock, not
        an error.

        Args:
            delta: signed decimal string, e.g. "-2.5" or "3". Must not be zero.
            reason: "adjustment" for a stocktake correction, "waste" for loss or
                damage. The choice is visible in the ledger.
            notes: why — this is the only explanation the ledger will carry.
        """
        if reason not in ("adjustment", "waste"):
            raise ToolError(
                f"reason must be 'adjustment' (stocktake correction) or 'waste' "
                f"(loss/damage), got {reason!r}"
            )
        if _dec(delta, "delta") == 0:
            raise ToolError("delta must be non-zero.")

        before = await client.get(f"/api/materials/{material_id}")
        args = {"material_id": material_id, "delta": delta, "reason": reason, "notes": notes}

        return await _logged(
            client, "adjust_material_stock", args, "material_movement",
            lambda: client.post(
                f"/api/materials/{material_id}/adjust",
                {"delta": delta, "reason": reason, "notes": notes},
            ),
            summarise=lambda r: (
                f"{r['name']} stock {before['stock_quantity']} -> {r['stock_quantity']} "
                f"({delta}, {reason})."
            ),
            object_id=lambda r: material_id,
        )

    # ── overhead ───────────────────────────────────────────

    @mcp.tool()
    async def create_overhead_material(
        name: str, unit: str, notes: str | None = None
    ) -> str:
        """Create an indirect/consumable material — tape, tools, studio supplies.

        Overhead carries no stock and no unit cost; it exists so dated expenses
        can be booked against it. If something is consumed per finished product,
        it belongs in `create_material` instead so it can join a recipe.
        """
        return await _logged(
            client, "create_overhead_material", {"name": name, "unit": unit},
            "overhead_material",
            lambda: client.post(
                "/api/overhead-materials",
                {"name": name, "unit": unit, "notes": notes},
            ),
            summarise=lambda r: f"Created overhead material {r['name']} ({r['unit']}).",
        )

    @mcp.tool()
    async def record_overhead_expense(
        overhead_id: str,
        total_cost: str,
        currency: str,
        shop_id: str | None = None,
        qty: str | None = None,
        supplier: str | None = None,
        invoice_no: str | None = None,
        received_at: str | None = None,
        notes: str | None = None,
    ) -> str:
        """Record a dated expense against an overhead material.

        Args:
            total_cost: decimal string — the whole expense, not a unit price.
            shop_id: attribute the expense to one shop, where it reduces that
                shop's profit. Omit for a general business cost; unallocated
                expenses are reported separately rather than split across shops.
            received_at: ISO 8601. Defaults to now — set it when back-entering an
                older invoice, since the P&L dates the expense by this.
        """
        _dec(total_cost, "total_cost")
        args = {
            "overhead_id": overhead_id, "total_cost": total_cost,
            "currency": currency, "shop_id": shop_id, "qty": qty,
            "supplier": supplier, "invoice_no": invoice_no, "received_at": received_at,
        }

        return await _logged(
            client, "record_overhead_expense", args, "overhead_receipt",
            lambda: client.post(
                f"/api/overhead-materials/{overhead_id}/receipts",
                {
                    "total_cost": total_cost, "currency": currency,
                    "shop_id": shop_id, "qty": qty, "supplier": supplier,
                    "invoice_no": invoice_no, "received_at": received_at,
                    "notes": notes,
                },
            ),
            summarise=lambda r: (
                f"Expense {total_cost} {currency}"
                f"{' (unallocated)' if not shop_id else ''} recorded."
            ),
        )

    # ── BOM (§5.5 wipe protection) ─────────────────────────

    async def _write_bom(product_id: str, lines: list[BomLine], tool: str, args: dict):
        payload = {
            "items": [
                {
                    "material_id": line.material_id,
                    "qty_per_unit": line.qty_per_unit,
                    "notes": line.notes,
                }
                for line in lines
            ]
        }
        return await _logged(
            client, tool, args, "bom",
            lambda: client.put(f"/api/products/{product_id}/bom", payload),
            summarise=lambda r: (
                f"Recipe now has {len(r['items'])} line(s); cost {r['cost']}."
            ),
            object_id=lambda r: product_id,
        )

    @mcp.tool()
    async def set_product_bom(
        product_id: str, items: list[BomLine], confirm_replace: bool = False
    ) -> str:
        """Replace a product's entire recipe.

        **This is a full replacement — any line you omit is deleted**, and there
        is no undo and no recipe history. As a guard, a call that would remove or
        change existing lines is refused unless `confirm_replace=True`; the
        refusal shows you exactly what would be lost.

        For a small edit prefer `add_bom_line` or `remove_bom_line`, which read
        the current recipe and change only what you name.

        Args:
            items: the complete recipe. An empty list clears it.
            confirm_replace: pass True once you have read the diff and mean it.
        """
        current = await client.get(f"/api/products/{product_id}/bom")
        diff = _diff_bom(current["items"], items)
        destructive = bool(diff["removed"] or diff["changed"])

        if destructive and not confirm_replace:
            raise ToolError(
                f"Refusing to replace this recipe — it would change existing "
                f"lines and cannot be undone:\n{_render_diff(diff)}\n\n"
                "Review the diff. To make only this change, use add_bom_line / "
                "remove_bom_line. To proceed with the full replacement, call "
                "again with confirm_replace=True."
            )

        args = {
            "product_id": product_id,
            "items": [line.model_dump() for line in items],
            "confirm_replace": confirm_replace,
            "diff": diff,
        }
        result = await _write_bom(product_id, items, "set_product_bom", args)
        return f"Applied:\n{_render_diff(diff)}\n\n{result}"

    @mcp.tool()
    async def add_bom_line(
        product_id: str,
        material_id: str,
        qty_per_unit: str,
        notes: str | None = None,
    ) -> str:
        """Add one material to a product's recipe, or change its quantity.

        Reads the current recipe and writes it back with just this line added or
        updated. Every other line is preserved, so this can never wipe a recipe.

        Args:
            qty_per_unit: decimal string — how much of this material one finished
                unit consumes, in the material's own unit.
        """
        _dec(qty_per_unit, "qty_per_unit")
        current = await client.get(f"/api/products/{product_id}/bom")

        lines = [
            BomLine(
                material_id=item["material_id"],
                qty_per_unit=str(item["qty_per_unit"]),
                notes=item.get("notes"),
            )
            for item in current["items"]
            if item["material_id"] != material_id
        ]
        replaced = len(lines) != len(current["items"])
        lines.append(
            BomLine(material_id=material_id, qty_per_unit=qty_per_unit, notes=notes)
        )

        args = {
            "product_id": product_id, "material_id": material_id,
            "qty_per_unit": qty_per_unit, "replaced_existing": replaced,
        }
        verb = "Updated" if replaced else "Added"
        result = await _write_bom(product_id, lines, "add_bom_line", args)
        return f"{verb} {material_id} at {qty_per_unit} per unit.\n{result}"

    @mcp.tool()
    async def remove_bom_line(product_id: str, material_id: str) -> str:
        """Remove one material from a product's recipe.

        Reads the current recipe and writes it back without this one line. Every
        other line is preserved.
        """
        current = await client.get(f"/api/products/{product_id}/bom")
        remaining = [
            BomLine(
                material_id=item["material_id"],
                qty_per_unit=str(item["qty_per_unit"]),
                notes=item.get("notes"),
            )
            for item in current["items"]
            if item["material_id"] != material_id
        ]
        if len(remaining) == len(current["items"]):
            raise ToolError(
                f"Material {material_id} is not in this recipe. Current lines: "
                f"{[i['material_name'] for i in current['items']] or 'none'}"
            )

        args = {"product_id": product_id, "material_id": material_id}
        result = await _write_bom(product_id, remaining, "remove_bom_line", args)
        return f"Removed {material_id} from the recipe.\n{result}"

    @mcp.tool()
    async def import_etsy_statement(
        shop_id: str, file_path: str, dry_run: bool = True
    ) -> str:
        """Import one monthly Etsy payment-account statement CSV.

        Derives each order's exact `platform_fee` from the statement's Fee and
        fee-VAT lines, and books advertising and listing/account fees to two
        monthly overhead rows for the shop. This is how Etsy orders get priced —
        the flat per-shop rate is for Shopify/WesternBid, where no such statement
        exists.

        `file_path` is a path on THIS machine. Give the operator's downloaded
        statement, one calendar month per file.

        **This writes money, so it rehearses first.** `dry_run` defaults to True:
        the import runs whole and is then rolled back, and you get the identical
        report without anything being written. Show that report to the operator,
        and only call again with `dry_run=False` once they have agreed to it.
        Never book a statement the operator has not seen the preview of.

        Safe to re-run: importing a month replaces that month's stored lines
        wholesale and recomputes the affected fees, so re-uploading the same file
        changes nothing, and a statement Etsy re-issued fully supersedes the
        original.

        The import refuses rather than guesses. A row it cannot classify — an
        unknown type, an unrecognised advertising line, a non-USD amount, a file
        spanning two months — aborts the whole import naming that row, and
        nothing is written. Report the message to the operator verbatim.

        Order numbers that this shop has no order for are counted and listed, not
        created. If there are many, the order CSV for that period probably has
        not been imported yet.
        """
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise ToolError(f"No file at {path}")
        if path.suffix.lower() != ".csv":
            raise ToolError(f"Expected a .csv statement export, got {path.name}")

        content = path.read_bytes()

        # The statement holds real financial data and customer order numbers, so
        # only the PATH is logged, never the contents — a CSV passed as a tool
        # argument would be persisted verbatim in agent_action_log.arguments.
        # `dry_run` IS logged: whether a call wrote or only rehearsed is the most
        # important thing about it in the audit trail.
        args = {"shop_id": shop_id, "file_path": str(path), "dry_run": dry_run}

        return await _logged(
            client,
            "import_etsy_statement",
            args,
            "etsy_statement",
            lambda: client.post_file(
                "/api/imports/etsy-statement",
                # Sent explicitly rather than relying on the API default, so the
                # agent's intent is on the wire either way.
                fields={"shop_id": shop_id, "dry_run": str(dry_run).lower()},
                filename=path.name,
                content=content,
            ),
            summarise=lambda r: (
                (
                    f"DRY RUN — nothing written. Statement {r['period']} would book: "
                    if r["dry_run"]
                    else f"Statement {r['period']} booked: "
                )
                + f"{r['lines_imported']} lines, {r['orders_matched']} orders priced"
                + (
                    f", {r['orders_unmatched']} unmatched"
                    if r["orders_unmatched"]
                    else ""
                )
                + f". Advertising {r['ads_overhead_amount']} and account fees "
                f"{r['account_fee_overhead_amount']} to overhead."
                + (
                    " Show this to the operator and call again with dry_run=False "
                    "to book it."
                    if r["dry_run"]
                    else ""
                )
            ),
            object_id=lambda r: r["period"],
        )
