# INTAKE-BOCHKAROV-7609 — book one leather-factory invoice to **PROD** via MCP

> **This is a data-entry record, not a code sprint.** No source files changed, no
> tests. Unlike the Dodon intake, this doc was written **after** the booking
> (2026-08-22): the spec travelled as a chat prompt from Cowork to CC; this file
> is the durable copy of both the spec and the outcome, per the
> `intake-2026-08-10-dodon-1996639047.md` precedent.

### Goal

Book **накладна №7609 від 20.08.2026** (new leather supplier, see "Supplier
identity" below) into the **production** warehouse: 2 lines of crazy-horse
half-hides, invoiced in USD ($165.25), paid **7 271,00 UAH**.

### Supplier identity — open tail

The invoice's «Від постачальника» field is blank. What we know: the contact was
recommended as **the factory itself** («саме завод»); manager phone
+380667635969; the Nova Poshta shipment arrived from sender «Бочкарьов Максим
Олексійович», 380991380215. Open-source lookup (2026-08-22) failed: neither
phone indexes publicly, and no leather factory matches the name. Candidate
factories producing crazy-horse half-hides (В-Центр/Вознесенськ, Чинбар) don't
list the invoice's colours publicly. Supplier recorded provisionally as
**«Шкірзавод (Бочкарьов)»**.

Consequence of append-only receipts: both receipt rows carry the provisional
name **permanently**. When the real legal name is learned (ask the manager):
update the ultramarine material's `supplier_name` via `update_material`, use the
real name on all future receipts, and record the alias mapping here — do not
attempt to "fix" the booked receipts.

### The invoice (source of truth — transcribed from the photo)

| # | Артикул | Товар | К-сть | Ціна (USD) | Сума (USD) |
|---|---|---|---|---|---|
| 1 | — | Крезі хорс галантерейний/напівшкіри/1,4-1,6/ультрамарин/без плити, 1 сорт | 1,73 м² | 32,00 | 55,36 |
| 2 | — | Крезі хорс Premium галантер./напівшкіри/1,4-1,6/запорошена троянда 123-12975/без плити, 1 сорт | 3,33 м² | 33,00 | 109,89 |

- **Усього з ПДВ: $165,25; ПДВ 0,00.** Номера специфікацій: 082931, 079401.
- Покупець: Петренко Сергій. Договір: основний.
- Paid **7 271,00 UAH** → implied spot rate **exactly 44,00** (165,25 × 44 =
  7 271,00 to the kopeck). This supplier's pattern: **USD invoice, settled in
  UAH at the spot rate** — expect to re-derive the rate from the payment on
  every future invoice.

### Currency and unit conversion (the two traps)

1. **USD → UAH at 44,00:** per-m² prices 32/33 USD → 1 408 / 1 452 UAH.
2. **m² → dm²:** the invoice is in m²; warehouse leather is in **dm²** (the
   existing pink card already was). Quantities ×100, prices ÷100 → 14,08 /
   14,52 UAH per dm². Booking the invoice's raw `qty=3.33` against the dm² pink
   card would have added 3,33 dm² instead of 333 and pulled its WAC up to
   ~23,7 — the conversion is mandatory, not stylistic. Zero rounding drift:
   both prices divide exactly.

### Booked — PROD, 2026-08-22 (received_at = 2026-08-20T12:00:00Z)

| # | Матеріал | К-сть | Ціна | Сума | receipt |
|---|---|---|---|---|---|
| 1 | Шкіра Крейзі Хорс 1,4-1,6мм ультрамарин (**created new**) | 173,00 dm² | 14,0800 | 2 435,84 | `c90a6099` |
| 2 | Шкіра Крейзі Хорс AN 1,4-1,6мм рожева (**existing** card) | 333,00 dm² | 14,5200 | 4 835,16 | `b7cbb9f9` |

Total **7 271,00 UAH** exact. `invoice_no = "7609"`, supplier «Шкірзавод
(Бочкарьов)», UAH, `shipping_cost` empty, `overhead_receipts` empty.

Weighted averages, verified independently:

- Ультрамарин: 0 → 173,00 dm², WAC 0 → **14,0800**.
- Рожева: 627,00 → 960,00 dm²; (627 × 16,1271 + 4 835,16) ÷ 960 = **15,5696**
  (down from 16,1271 — correct direction, new price below the old average).
- No other material moved (all six other crazy-horse rows byte-identical).

### Decisions taken (settled)

1. **Pink identity.** «Крезі хорс Premium, запорошена троянда 123-12975» **is**
   the existing «Шкіра Крейзі Хорс AN 1,4-1,6мм рожева» (confirmed by Sergii —
   same material, previously bought from ФОП Додон). Exactly one candidate
   matched; receipt booked against it, **no new material created**.
2. **Pink card untouched.** Name, `supplier_name` (ФОП Додон) and
   `supplier_sku` (032053) unchanged; Бочкарьов, Premium grade and colour code
   «запорошена троянда 123-12975» recorded in the **receipt notes** only. The
   card is now **mixed-supplier**: its WAC blends Додон and Бочкарьов
   deliveries — compare future quotes per supplier, not against the blended
   average.
3. **No supplier article.** The invoice's «Артікул» column is empty; the
   specification numbers 082931/079401 look like batch/spec numbers, not stable
   product codes → no `supplier_sku` set. **Dedup key for this supplier is the
   name** (colour + thickness), until a stable article system shows up.

### Open tails (none blocking)

- **(a) Real supplier name unknown** — see "Supplier identity" above.
- **(b) Colour code 123-12975 is unsearchable:** it lives only in receipt
  notes; `list_materials(search=…)` covers name and `supplier_sku`, not notes.
  Same tail as Додон's 019296.
- **(c) `docs/warehouse/bom-source-data.md:62-67`** caches stale WACs (рожева
  16.1271, чорна 12.7539) — stale since before this intake (the August Dodon
  invoice isn't reflected either). It is a point-in-time snapshot, not a live
  reference; deliberately not updated here.

### Context

- MCP tool list + safety rails: `mcp_server/README.md`.
- Prod connection (Cloudflare Access service token, agent creds):
  `docs/integrations/mcp-server.md`.
- Precedent for this flow and this doc's format:
  `docs/warehouse/intake-2026-08-10-dodon-1996639047.md`; earlier loads:
  2026-08-02 ФОП Додон (8 invoices), 2026-08-14 HandyMarket / MERKON.
