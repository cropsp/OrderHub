# BOM intake convention — turning a cut into a recipe

> **Audience:** whoever builds a product's BOM (recipe) via Claude Code + the
> `orderhub` MCP. This is the shared rulebook so recipe #1 and recipe #50 are
> costed the same way. Validated on the Bat ID Wallet pilot (2026-08-02).
>
> **Cowork owns this file, Sergii commits it, CC reads it.** It is a *convention*,
> not code — the arithmetic lives in CC's reasoning + the existing MCP tools, not in
> the backend (deliberate: the formulas are trivial and the operator wants per-line
> manual override).

## What a BOM is

A recipe is **quantities**, not money: "this product consumes X dm² of leather
027515 + Y m of thread S999 + Z pcs hardware + cutting + sewing." The cost is
derived by the system: `Σ(qty × material current_unit_cost × (1 + waste%))`. So the
input we capture per product is the **material breakdown + quantities**, in each
material's own unit.

BOM attaches to a **product**, not a variant (`compute_bom_cost` is per product).
Colour variants that would differ only in the leather material therefore need a
product/variant split to carry different recipes — today Bat ID Wallet has a single
variant, so its one recipe covers it.

## The intake template

For each product, capture and enter:

| Line | Material | Unit | Quantity from | Notes |
|---|---|---|---|---|
| Leather | the colour's article (e.g. 027515 black) | `dm²` | overall **blank** area from the cut screenshot | net blank area; waste_percent adds offcuts (see below) |
| Thread | S999 / S021 | `m` | measured actual length if known, else **seam length × 3** | ×3 is the default saddle-stitch factor; a measured value overrides it |
| Hardware | ring d25 / d30, strap blank, … | `pcs` | count per unit | integer counts; omit if the product has none |
| Cutting | `Лазерна порізка` (shared) | `m` | total cut / knife-path length from the screenshot | rate × cut length |
| Sewing | `Пошиття <product>` (per-product) | `pcs` | 1 | outsource rate for *this* product |

Record the derivation in **each line's `notes`**, e.g.
`"5.85 dm² = blank 18.05×32.41 cm (gabaryt)"`, `"1.80 m measured actual"`,
`"3.43 m cut length × 16 UAH/m"`, `"outsource sewing 60 UAH"`.

### Units and the 2-decimal cap

`bom_items.qty_per_unit` is `Numeric(8,2)` — quantities round to 2 dp, and a
`qty > 0` check **rejects** anything that rounds to 0.00 (loud, not silent). So pick
the unit where the per-product quantity sits comfortably ≥ 0.01: leather in dm²,
thread/cutting in m, hardware/sewing in pcs. If a future consumable would be a tiny
fraction of its unit (e.g. finish in litres), enter it in a smaller unit (ml).

## Cost model — where labour and cutting live

The system has no dedicated "labour/service" concept, so per-unit procured services
are modelled as **materials** (a material is really any cost-input consumed per
unit). Two shapes:

- **Cutting — one shared material.** `Лазерна порізка`, unit `m`, one rate
  (16 UAH/m today). Quantity per product = that product's cut length. Reusable.
- **Sewing — one material per product.** `Пошиття <product>`, unit `pcs`, the
  outsource price for *that* product (a wallet ≠ a bag), quantity 1. It is per
  product because the rate varies by product.

A service material's rate is set with **one rate-setting receipt**
(`record_material_receipt qty 1, unit_cost <rate>`), since `current_unit_cost` only
moves through receipts. Give it no `supplier_sku`.

**Known caveat (filed, not fixed):** these service materials are not really stocked,
so every shipped unit decrements them into negative stock and adds a "stock went
negative" warning to the order. Harmless to the cost; a real "non-stocked / service"
flag is the eventual fix.

## Waste

`waste_percent` lives on the **material** (global to that material — the same offcut
rate applies to every product using that leather), and it is applied to **both** the
booked COGS on shipment **and** the reviewed preview cost (fixed in `BOM-WASTE-1`,
`fix(bom)` 3257b13 — before that the preview silently excluded it). Enter **net**
area in the BOM; do not pre-add offcuts. Set the real offcut % on each leather when
you decide it; leave 0 to mean "no allowance".

## Currency

Materials are UAH. **`FX-CONVERSION`** (on `feat/mcp-warehouse`, commits `1a1f396` /
`fe410de` / `447c365` — not yet merged/deployed) introduced a single **UAH→USD** rate,
so USD-shop orders now book a USD COGS:

- **Rate source:** the NBU public API, auto-fetched daily by the scheduler + a manual
  override; editing it is OWNER-only and audited. **Direction: UAH→USD is division by
  the rate** (rate = UAH per 1 USD, e.g. 190.43 UAH ÷ 44.64 ≈ $4.27) — never multiply.
- **Snapshot at ship:** the order stores the converted COGS + the UAH basis
  (`cogs_basis_amount`) + the rate used, so changing the rate later never moves an
  already-shipped order.
- **Preview:** `compute_product_cost` takes an explicit **target currency** and returns
  the converted figure (so it matches what will book); the UAH basis stays visible.
- **All-or-nothing:** if any material-currency bucket can't convert (e.g. a stray EUR
  order, or no rate cached), the whole COGS stays `None` + a warning — never a partial,
  profit-inflating figure. **Stock is still consumed** regardless, so inventory stays
  accurate.
- KoraKlenu (UAH orders) is same-currency — books directly, rate NULL, unchanged.

Real order currencies are USD + UAH only; anything else degrades via the all-or-nothing
rule. Historical already-shipped orders keep their NULL cost until a separate
`historical-COGS-recompute` (NBU's `date=` param makes per-date lookup possible).

## Worked example — Bat ID Wallet (the pilot)

Product `b0e6c91b-8364-41df-bb7a-9924507369eb` (Lamamarka Shopify), one variant.

| Line | Material | Qty | Unit cost | Line cost |
|---|---|---|---|---|
| Leather | 027515 Crazy Horse AN black | 5.85 dm² | 12.7539 | 74.61 |
| Thread | Galaces S999 black | 1.80 m | 0.5204 | 0.94 |
| Cutting | Лазерна порізка | 3.43 m | 16.0000 | 54.88 |
| Sewing | Пошиття Bat ID Wallet | 1 pcs | 60.0000 | 60.00 |
| **Total (waste 0)** | | | | **190.43 UAH** |
| Total (leather waste 15%) | leather line → 85.80 | | | **201.62 UAH** |

At ~41 UAH/$ that is ≈ $4.6 of production cost against a $29.99 price — a healthy
margin. Composition: leather 39%, cutting 29%, sewing 31%, thread <1%.

## How to run it (CC prompt shape)

Open a CC session with the MCP connected, then, per product: name the product +
variant, attach the cut screenshot(s), name the materials (leather article, thread,
hardware). CC states the screenshot's measurement unit first (never assumes), reads
net blank area → dm² and cut length → m, applies thread measured-or-×3, adds each
line with `add_bom_line` (derivation in notes), and runs `compute_product_cost` for
you to eyeball. Create the two service materials once (`Лазерна порізка` + a per-
product `Пошиття …`) with rate-setting receipts if they don't exist yet.
