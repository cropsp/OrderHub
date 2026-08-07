# Брифінг: поточна архітектура складу в OrderHub

**Дата:** 2026-08-07
**Призначення:** вхідні дані для опрацювання архітектурних рішень по складу (пакування, витратники, списання).
**Статус:** опис фактичного стану коду на `main`. Жодних змін не вносилось.

Усе нижче звірено безпосередньо з кодом. Посилання на файли — шляхи від кореня репозиторію.

---

## 1. Головний факт

У OrderHub **дві незалежні, неспоріднені підсистеми складу**. Вони не знають одна про одну, мають різні моделі даних, різні тригери списання і різне покриття MCP-тулами.

| | **Packaging** (PKG-1, PKG-1b, PKG-2) | **Materials** (MAT-1 … MAT-6) |
|---|---|---|
| Основна таблиця | `packaging_boxes` | `materials` + `overhead_materials` |
| Журнал руху | `packaging_stock_movements` | `material_movements` |
| Прибуткування | немає окремої сутності | `material_receipts`, `overhead_material_receipts` |
| Собівартість одиниці | **немає взагалі** | `current_unit_cost`, середньозважена |
| Артикул постачальника | **немає поля** | `supplier_sku` + `supplier_name` |
| Валюта | немає | є, per-material, з FX-конверсією |
| Входить у собівартість замовлення | **ні** | так, через BOM |
| Тригер списання | створення ТТН | перехід замовлення в `SHIPPED` |
| Зв'язок з товаром | немає (підбір за геометрією) | `bom_items` |
| Scope | глобальний, без прив'язки до магазину | глобальний |
| MCP-тули | **жодного** | 8 read + 11 write |

Це розходження — центральне питання для проєктування. Пакування зараз існує **виключно як геометрія для калькулятора посилки**, а не як складська позиція з вартістю.

---

## 2. Підсистема Packaging

### 2.1 `packaging_boxes` — `backend/models/packaging.py`

```python
class PackagingType(str, enum.Enum):
    BOX = "BOX"
    ENVELOPE = "ENVELOPE"        # PG enum "packaging_type", create_constraint=True
```

| Поле | Тип | Обмеження |
|---|---|---|
| `id` | UUID | PK |
| `name` | String(100) | NOT NULL |
| `packaging_type` | enum | NOT NULL, default `BOX`, indexed |
| `inner_length_mm` | Integer | NOT NULL, `> 0` (валідація в Pydantic) |
| `inner_width_mm` | Integer | NOT NULL, `> 0` |
| `inner_height_mm` | Integer | NOT NULL, `> 0` |
| `max_thickness_mm` | Integer | nullable — **тільки для ENVELOPE**; NULL = перевірка лише за вагою |
| `max_weight_g` | Integer | **NOT NULL, `> 0`** |
| `tare_weight_g` | Integer | NOT NULL, default 0 |
| `sort_order` | Integer | NOT NULL, default 0 |
| `stock_quantity` | Integer | NOT NULL, default 0 — кешований лічильник |
| `low_stock_threshold` | Integer | NOT NULL, default 5 |
| `created_at` / `updated_at` | timestamptz | `TimestampMixin` |

**Чого немає:** ціни, собівартості, валюти, артикула/SKU, постачальника, матеріалу (гофра/мікрогофра/картон), зовнішніх розмірів, нотаток, прапорця `is_active` (тільки hard-delete).

**Наслідок:** артикул «Упаковочки» немає куди покласти. Немає ключа, що зв'язує коробку між накладними — тобто того, що в `materials` вирішено полем `supplier_sku` (див. коментар у `models/material.py:70-75`).

### 2.2 `packaging_stock_movements` — `backend/models/stock_movement.py`

```python
class StockMovementReason(str, enum.Enum):
    INITIAL_STOCK = "initial_stock"
    RESTOCK       = "restock"
    TTN_CREATE    = "ttn_create"
    TTN_DELETE    = "ttn_delete"
    ADJUSTMENT    = "adjustment"
```

Поля: `box_id` (FK CASCADE), `order_id` (FK SET NULL, nullable), `delta` (Integer, NOT NULL), `reason`, `note`, `user_id` (FK RESTRICT), `created_at` (timestamptz, `server_default=func.now()`, indexed).

Гібридний event-sourcing: `PackagingBox.stock_quantity` — це кешована сума `delta`, мутується транзакційно разом зі вставкою рядка журналу.

### 2.3 `services/stock_service.py::apply_movement`

Єдина точка зміни залишку. Не комітить — транзакцію тримає викликач. Повертає список попереджень; якщо після `delta` лічильник пішов у мінус — попередження, але **операція не блокується** (від'ємний залишок дозволений).

**Сигнатура не має параметра дати.** `created_at` завжди береться з `server_default`. Тобто чинним кодом заднім числом рух не запишеш.

### 2.4 Де списується

`backend/routers/shipping.py`:
- рядок ~300 — створення ТТН → `apply_movement(delta=-1, reason=TTN_CREATE, order_id=...)`
- рядок ~381 — видалення ТТН → `apply_movement(reason=TTN_DELETE)`

Тобто **пакування списується на створенні ТТН, а не на статусі замовлення**.

### 2.5 Зв'язок із замовленням

У `models/order.py` **два різні FK** на `packaging_boxes`:

- `computed_packaging_box_id` (рядок 246) — що підібрав калькулятор посилки (`services/parcel_calculator.py`), за геометрією та вагою
- `packaging_id` (рядок 252) — що обрав оператор вручну (PKG-1)

Зв'язку «товар → його коробка» **не існує ніде**. BOM (`bom_items`) містить виключно `material_id`.

### 2.6 REST-ендпоінти — `backend/routers/packaging.py`

| Метод | Шлях | Роль |
|---|---|---|
| GET | `/api/packaging-boxes` | будь-який автентифікований |
| POST | `/api/packaging-boxes` | OWNER, MANAGER |
| POST | `/api/packaging-boxes/{box_id}/restock` | OWNER, MANAGER |
| PATCH | `/api/packaging-boxes/{id}` | OWNER, MANAGER |
| DELETE | `/api/packaging-boxes/{id}` | OWNER, MANAGER — **hard delete** |
| POST | `/api/packaging-boxes/bulk-csv/preview` | OWNER, MANAGER |
| POST | `/api/packaging-boxes/bulk-csv/confirm` | OWNER, MANAGER |

`POST /api/packaging-boxes` приймає додатково `initial_quantity` (≥0) і `low_stock_threshold` (≥0, default 5). При `initial_quantity > 0` пишеться рядок журналу `initial_stock`.

**Колонки CSV** (`services/import_service.py::validate_packaging_csv`, рядки 104-125) — рівно ці, інші ігноруються:

```
name, packaging_type, inner_length_mm, inner_width_mm, inner_height_mm,
max_thickness_mm, max_weight_g, tare_weight_g, sort_order
```

Дефолти при відсутності: `packaging_type=BOX`, решта числових = 0 → а оскільки Pydantic вимагає `> 0`, рядок без розмірів або без `max_weight_g` **впаде у помилку валідації**. `initial_quantity` та `low_stock_threshold` через CSV **не передаються** — коробки імпортуються з нульовим залишком.

---

## 3. Підсистема Materials

`backend/models/material.py`. Дві паралельні сутності за settled-decision #1 дизайн-документа.

### 3.1 `materials` — прямі матеріали

`name` (200), `unit` (20), `currency` (3), `current_unit_cost` Numeric(12,4), `stock_quantity` Numeric(12,2), `low_stock_threshold`, `waste_percent` Numeric(5,2), `supplier_name` (200, nullable), `supplier_sku` (100, nullable, indexed, **не unique**), `notes` (Text), `is_active` (Boolean — м'яке архівування).

Входять у BOM, списуються при відвантаженні, формують `computed_production_cost` замовлення.

### 3.2 `overhead_materials` — непрямі/витратники

`name`, `unit`, `notes`, `is_active`. **Без залишку і без собівартості** — існують лише щоб вішати на них датовані витрати. Ніколи не списуються.

### 3.3 `material_receipts` — прибуткування

`material_id`, `qty`, `unit_cost` Numeric(12,4), `currency`, `shipping_cost` (nullable), `is_initial` (Boolean), `supplier` (200), `invoice_no` (100), **`received_at` (timestamptz, задається явно)**, `notes`, `user_id`.

Кожен receipt перераховує середньозважену `current_unit_cost` через `services/material_stock_service.py::apply_receipt`.

**`received_at` приймається явно** — тобто прибуткування заднім числом працює вже зараз. Це принципова відмінність від `material_movements` / `packaging_stock_movements`, де дата тільки серверна.

### 3.4 `overhead_material_receipts`

`overhead_material_id`, `shop_id` (nullable → «нерозподілене»), `qty` (nullable), `total_cost`, `currency`, `supplier`, `invoice_no`, `received_at`, `notes`, `source_ref` (маркер автоімпортера, унікальний індекс по `(shop_id, source_ref)` де `source_ref IS NOT NULL`), `user_id`.

### 3.5 `material_movements` — журнал

```python
class MaterialMovementReason(str, enum.Enum):
    RECEIPT = "receipt"; CONSUMPTION = "consumption"
    WASTE = "waste";     ADJUSTMENT = "adjustment"
```

`material_id`, `delta`, `reason`, `order_id` (nullable), `receipt_id` (nullable), `unit_cost_at_movement` (nullable), `notes`, `user_id`, `created_at` (`server_default`).

CHECK-обмеження `ck_material_movement_consumption_cost`: `unit_cost_at_movement` обов'язкове **тоді й лише тоді**, коли `reason='consumption'`.

### 3.6 Списання — `services/order_consumption_service.py` (MAT-4)

Викликається з `order_service.change_order_status()` при переході замовлення в **SHIPPED**, після запису `OrderStatusHistory`, до коміту.

1. **Ідемпотентність:** якщо вже є `material_movements` з `order_id = order.id AND reason='consumption'` → no-op. Захищає від повторного SHIPPED.
2. Обхід `OrderItems → ProductVariant → Product → BomItem`; `actual_consumed = qty_per_unit × order_item.quantity × (1 + waste_percent/100)`.
3. Накопичення вартості **по валютних кошиках**, конверсія в валюту замовлення, округлення **один раз** наприкінці.
4. Якщо хоч один кошик неможливо сконвертувати — **весь розрахунок собівартості скасовується** (`computed_production_cost=None` + попередження), але **рухи списання все одно пишуться** (залишок лишається чесним). Обґрунтування в докстрінгу: занижений COGS завищує чистий прибуток і переплачує партнерські виплати мовчки; відсутнє число відновлюване, правдоподібно-хибне — ні.

---

## 4. MCP-сервер: що є, чого немає

Окремий локальний stdio-процес у `mcp_server/`, ходить у власний REST API як користувач-агент з роллю MANAGER. Записи аудуються в `agent_action_log`.

### Read-тули (`mcp_server/tools_read.py`)

`list_shops`, `list_materials`, `get_material`, `list_material_receipts`, `list_material_movements`, `list_receipts_by_invoice`, `list_overhead_materials`, `list_overhead_expenses`, `list_products`, `get_product`, `get_product_bom`, `compute_product_cost`, `check_parcel_delivery`

### Write-тули (`mcp_server/tools_write.py`)

`create_material`, `update_material`, `archive_material`, `record_material_receipt`, `adjust_material_stock`, `create_overhead_material`, `record_overhead_expense`, `set_product_bom`, `add_bom_line`, `remove_bom_line`, `import_etsy_statement`

### Прогалина

**Жодного тула для пакування.** Ані читання, ані створення, ані поповнення залишку. `check_parcel_delivery` — єдине, що дотично стосується посилок.

Отже сценарій «агент вносить коробки на склад через MCP» **зараз нездійсненний**. Три варіанти: CSV-імпорт через UI (нуль коду), дописати тули в MCP, або дьоргати REST напряму.

### Корисні деталі з наявних тулів

- `create_material` має **два guard-и проти дублів**: спершу за `supplier_sku` (сильніший сигнал — саме випадок «один матеріал по-різному написаний у двох накладних»), потім за точною назвою. Обидва відмовляють із поясненням, а не мовчки створюють другий рядок.
- `record_material_receipt` приймає `received_at`, `supplier`, `invoice_no` → історія закупівель з датами лягає один-в-один.
- `create_overhead_material` у докстрінгу прямо каже: якщо позицію треба буде включити в рецептуру — їй місце в `create_material`, а не в overhead.

---

## 5. Відкриті питання

### Q1. Де живе вартість пакування?

Коробки **не мають ціни й не входять у `computed_production_cost`**. `order_consumption_service` рахує тільки матеріали з BOM. Тобто зараз пакування не потрапляє ні в COGS фінансової сторінки, ні в базу партнерських виплат по формулі `PROFIT`.

Варіанти:
- **(a)** додати в `packaging_boxes` поля вартості + власну сутність прибуткування → дублювання всієї логіки `materials` (середньозважена, валюти, FX)
- **(b)** завести коробку одночасно як `Material` і як `PackagingBox`, зв'язати FK → два записи на один фізичний об'єкт, ризик розсинхрону залишків
- **(c)** перенести пакування в `materials` повністю, лишивши в `packaging_boxes` **тільки геометрію** для калькулятора посилки → одна модель вартості, але потрібна міграція і переписування точки списання
- **(d)** вважати пакування overhead-витратою → просто, але вартість не спуститься до конкретного замовлення

Наслідки зачіпають `finance_service` (картки COGS), партнерські виплати (`docs/design/profit-definition.md`) і `NETPROFIT-RECONCILE`.

### Q2. Тільки два типи пакування

`PackagingType` = `BOX | ENVELOPE`. Пакети, наповнювач, бульбашкова плівка, скотч, стрічки, папір — **не влазять**. Або розширювати PG-enum міграцією (з урахуванням обмеження PG16 на `ALTER TYPE … ADD VALUE` в одній транзакції — це вже кусало в PARTNER-CONFIG-1), або відправляти їх у `materials` / `overhead_materials`.

### Q3. Списання заднім числом

Ані `PackagingStockMovement`, ані `MaterialMovement` не приймають дату — обидва мають `created_at` з `server_default=func.now()`, а `apply_movement` в обох сервісах не має відповідного параметра. Поле в моделі є, тож на рівні ORM дату проставити можна, але **жоден наявний шлях (REST, сервіс, MCP) цього не робить**.

Для ретроспективного списання по вже виконаних замовленнях потрібно вирішити:
- параметр `occurred_at` в `apply_movement` + surface, який його приймає
- чи має ретроспективний рух змінювати **поточний** кешований лічильник (майже напевно так — інакше журнал і лічильник розійдуться)
- ідемпотентність: у matarials вона вже є через `(order_id, reason='consumption')`; у packaging **аналогічного guard-а немає** — повторний прогін спише вдруге
- від'ємний залишок не блокується, тож масовий backfill тихо заведе лічильники в мінус

### Q4. Різні тригери списання

Пакування списується на **створенні ТТН**, матеріали — на переході в **SHIPPED**. Для історичних замовлень треба визначитись, від чого відштовхуватись: `ttn_created_at`, `shipped_at` чи `ordered_at`. Замовлення без ТТН (самовивіз, міжнародна відправка іншим способом) — окремий випадок.

### Q5. Немає зв'язку «товар → коробка»

Зараз коробка або підбирається калькулятором за геометрією, або ставиться оператором вручну на замовлення. Щоб «підв'язати кожну коробочку під виріб», потрібне одне з:
- рядок пакування в BOM (вимагає, щоб пакування було `Material` — див. Q1(c))
- поле `default_packaging_box_id` на `ProductVariant` або `Product`
- окрема таблиця відповідності

Плюс правило для замовлень з кількох позицій: коробка одна на посилку, а не одна на товар. Калькулятор посилки це вже вміє — треба не зламати.

### Q6. Немає ключа постачальника в пакуванні

У `packaging_boxes` немає `supplier_sku` / `supplier_name` / `notes`. Артикул «Упаковочки» немає куди записати, тобто немає стабільного ключа для повторного зіставлення при наступних закупівлях. У `materials` ця задача вже вирішена — сильний аргумент на користь Q1(c).

### Q7. Hard delete

`DELETE /api/packaging-boxes/{id}` видаляє фізично, каскадом зносячи весь журнал руху. У `materials` натомість м'яке архівування через `is_active`. Для коробки, на яку посилаються історичні замовлення (`order.packaging_id`, `computed_packaging_box_id` → обидва `ondelete=SET NULL`), це означає тиху втрату історії.

---

## 6. Що з цим робити далі

Порядок, у якому питання варто розв'язувати — бо кожне наступне залежить від попереднього:

1. **Q1** — визначити модель вартості пакування. Це кореневе рішення, від нього залежить усе інше.
2. **Q2** — визначити межу: що є «пакування», а що «матеріал/overhead».
3. **Q5** — спроєктувати зв'язок товар↔пакування (форма залежить від Q1).
4. **Q3 + Q4** — спроєктувати ретроспективне списання.
5. **Q6, Q7** — гігієна схеми, вирішується разом з Q1.
6. Тули MCP для пакування — **в останню чергу**, коли схема усталиться. Інакше доведеться переписувати.
