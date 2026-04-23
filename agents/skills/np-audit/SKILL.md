# Nova Poshta Integration — Technical Audit Report
**Project:** OrderHub CRM  
**Scope:** TTN creation pipeline, NP API client, shipping router, frontend logistics UI  
**Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 async · React 19 / TypeScript  
**Date:** April 2026

---

## Executive Summary

The integration is structurally sound and demonstrates good architectural instincts — encrypted keys, async HTTP, retries, proper Ref-based addressing. However, there are **three categories of issues** that will prevent the feature from working reliably in production:

1. **Critical bugs** that will cause TTN creation to fail silently or corrupt data.
2. **Missing business-logic** required for real Ukrainian e-commerce operations (COD, etc.).
3. **UX/data consistency issues** in the frontend that can produce invalid shipping data.

The sections below describe every issue, its severity, its root cause, and a concrete fix recommendation.

---

## 1. Backend — `nova_poshta.py`

### 1.1 `build_ttn_payload` is dead code with incorrect field values
**Severity: High**

The `build_ttn_payload` helper function at the bottom of `nova_poshta.py` is never called. The actual payload is assembled inline inside `shipping.py`. The dead function is dangerous because it contains a fundamental mistake:

```python
# WRONG — NP expects a UUID Ref for "Sender", not a name string
"Sender": sender_last,
"Recipient": f"{recipient_last} {recipient_first} {recipient_middle}".strip(),
```

The Nova Poshta `InternetDocument/save` API requires that `Sender` and `Recipient` fields contain the counterparty's UUID `Ref` (e.g. `"a9d3b5e2-0000-..."`), not a human-readable name. Passing a name string causes the API to return an error response (`success: false`).

**Fix:** Delete `build_ttn_payload` entirely. It is not used, it is wrong, and its presence misleads future developers about the expected field types.

---

### 1.2 Retry strategy catches all exceptions including non-retryable NP business errors
**Severity: High**

```python
retry=retry_if_exception_type((httpx.HTTPError, Exception))
```

The retry decorator catches `Exception` — which is every Python exception. This means NP business-logic errors (e.g., "Counterparty not found", "Warehouse does not exist") that are returned as `success: false` in the 200-OK body are manually raised as `Exception` and then retried 3 times with exponential backoff.

This has two consequences:
- TTN creation takes up to `2 + 4 + 8 = 14 extra seconds` on any validation error before finally failing.
- On recipient creation (`create_counterparty`), three retry attempts could create the same counterparty three times in the NP system.

**Fix:** Create a dedicated exception class for NP API-level business errors, and only retry on transport-level errors:

```python
class NovaPoshtaAPIError(Exception):
    """Raised when NP returns success=false. Never retryable."""
    pass

retry=retry_if_exception_type(httpx.HTTPError)
# Then inside _post, raise NovaPoshtaAPIError instead of Exception
```

---

### 1.3 New `httpx.AsyncClient` created per API call — no connection pooling
**Severity: Medium**

```python
async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
```

Each call to `_post` opens and closes a new TCP/TLS connection to `api.novaposhta.ua`. A single TTN creation makes 4-5 sequential calls, meaning 4-5 full TLS handshakes per order. This adds ~200-400ms of unnecessary overhead.

**Fix:** Accept an `httpx.AsyncClient` as an optional constructor argument or use a class-level shared client:

```python
class NovaPoshtaClient:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=30.0, follow_redirects=True)
```

In FastAPI, inject a shared client via application lifespan (`app.state.http_client`).

---

### 1.4 `get_counterparty_addresses` is defined but never used
**Severity: Low**

The method exists in `NovaPoshtaClient` but is not called anywhere. If it was originally part of an automatic sender-address-resolution flow that was removed, the method should be removed too to keep the client surface clean.

---

## 2. Backend — `shipping.py`

### 2.1 Missing validation of `shipping_city_ref` and `shipping_warehouse_ref` before payload construction
**Severity: Critical**

The endpoint validates:
```python
if not order.shipping_city or not order.shipping_name or not order.shipping_phone:
    raise HTTPException(...)
```

But it does **not** validate `order.shipping_city_ref` or `order.shipping_warehouse_ref` before using them directly in the payload. These values can be `None` if the order was imported from Shopify or edited via the free-text non-UA form path. When they are `None`, the payload passes `"CityRecipient": None` to NP, which causes the API to return an opaque validation error.

**Fix:** Add explicit guards immediately after the existing validation block:

```python
if not order.shipping_city_ref or not order.shipping_warehouse_ref:
    raise HTTPException(
        status_code=400,
        detail="Order is missing NP city reference or warehouse reference. "
               "Please select the recipient city and branch using the shipping editor."
    )
```

---

### 2.2 `db.flush()` instead of `db.commit()` — TTN number may not persist
**Severity: Critical (data loss)**

```python
await db.flush()
return {"status": "success", "ttn": order.ttn_number}
```

`flush()` sends the UPDATE to the database connection but does not commit the transaction. Whether this persists depends entirely on whether there is session-commit middleware (e.g., a middleware that commits after each successful response). If no such middleware exists, the `order.ttn_number` update will be rolled back when the session closes.

This creates the worst possible failure mode: the TTN is registered at Nova Poshta, the user sees a success response, but on the next page refresh `order.ttn_number` is `None` and the button is available again — potentially leading to a duplicate TTN creation attempt.

**Fix:** Use `await db.commit()`:

```python
await db.commit()
await db.refresh(order)
return {"status": "success", "ttn": order.ttn_number}
```

---

### 2.3 Five sequential external API calls with no caching — slow and fragile
**Severity: High**

The `create_np_ttn` endpoint makes the following calls to NP in sequence:

1. `get_counterparties("Sender")` — to find sender Ref
2. `get_contact_persons(sender_ref)` — to find sender contact Ref
3. `get_counterparties("Recipient", phone)` — to find or verify recipient
4. `get_contact_persons(recipient_ref)` OR `create_counterparty(...)` — to find/create recipient contact
5. `create_internet_document(payload)` — actual TTN creation

Steps 1 and 2 return data that never changes between orders (the sender is always the same shop). Fetching them on every single TTN creation is wasteful and adds ~500-800ms of latency.

**Fix:** Cache sender data in the `Shop` model or in Redis/memory cache keyed by `shop_id`. Sender `Ref`, sender contact `Ref`, and sender phone should be resolved once during shop NP setup and stored alongside `np_sender_city_ref`.

```python
# During shop NP configuration save:
shop.np_sender_ref = sender_ref
shop.np_sender_contact_ref = sender_contact_ref  
shop.np_sender_phone = sender_phone
```

Then in `create_np_ttn`, skip calls 1 and 2 entirely if these fields are populated.

---

### 2.4 `VolumeGeneral: "0.001"` is unrealistically small and will fail NP validation
**Severity: High**

The volume `0.001` cubic meters equals 1 cubic centimeter — smaller than a sugar cube. The Nova Poshta API has a minimum volumetric threshold and will reject or auto-correct payloads below it. This will surface as an opaque API error in production.

The standard minimum for a small parcel is `0.0004` m³ (e.g., 10×10×4 cm). A sensible default for e-commerce is `0.001`–`0.004` m³. This should be a configurable shop-level setting (`np_default_volume_m3`) with a safe minimum fallback of `0.001`.

```python
volume = body.volume or shop.np_default_volume_m3 or 0.004
payload["VolumeGeneral"] = str(volume)
```

---

### 2.5 `PaymentMethod` and `PayerType` are hardcoded — no support for prepaid orders
**Severity: High**

```python
"PayerType": "Sender",
"PaymentMethod": "Cash",
```

For Ukrainian e-commerce, many orders are prepaid (transferred via Monobank, PrivatBank). For those, `PaymentMethod` should be `"NonCash"`. For orders where the recipient pays for delivery (the most common COD model in Ukraine), `PayerType` should be `"Recipient"`.

These should be shop-level defaults that can be overridden per order.

---

### 2.6 Missing `BackwardDeliveryData` — no cash-on-delivery (COD) support
**Severity: High (missing critical feature for UA e-commerce)**

Cash-on-delivery (накладений платіж) is the dominant payment model in Ukrainian e-commerce. When a COD order is shipped via NP, the payload must include:

```json
"BackwardDeliveryData": [{
    "PayerType": "Recipient",
    "CargoType": "Money",
    "RedeliveryString": "1500"
}]
```

Where `RedeliveryString` is the declared order value in UAH that NP will collect from the recipient and remit back to the sender.

Without this, COD orders will be shipped but NP will not collect payment from the recipient.

**Fix:** Add a `cash_on_delivery` boolean and `cod_amount` field to `CreateTTNRequest`. If `cash_on_delivery` is true, append `BackwardDeliveryData` to the payload using the order's total price (or a custom amount).

---

### 2.7 No atomic handling: TTN registered at NP but DB update can fail
**Severity: Medium**

If `create_internet_document` succeeds (TTN created at NP) but the subsequent `db.commit()` fails (e.g., DB connection timeout), the system ends up in an inconsistent state: a real TTN exists in the NP system with no corresponding record in the CRM.

**Fix:** Log the TTN response immediately before attempting any DB operation:

```python
ttn_number = ttn_data.get("IntDocNumber")
logger.info(f"NP TTN created: {ttn_number} for order {order_id} — persisting to DB")
order.ttn_number = ttn_number
try:
    await db.commit()
except Exception as db_err:
    logger.critical(
        f"CRITICAL: TTN {ttn_number} created at NP but DB commit failed for order {order_id}: {db_err}"
    )
    raise
```

Consider also adding a separate endpoint to manually set `ttn_number` on an order as a recovery path.

---

### 2.8 No TTN deletion or status tracking endpoints
**Severity: Medium (operational gap)**

In production, operators need to:
- **Delete a TTN** when an order is cancelled before handoff (`InternetDocument/delete`)
- **Track a TTN status** to know if a shipment has been received, is in transit, or was returned (`TrackingDocument/getStatusDocuments`)

Without these, managers will need to go to the NP personal cabinet manually for any post-creation operations.

**Recommended additions:**

```python
DELETE /api/shipping/np-ttn/{order_id}  # calls InternetDocument/delete
GET    /api/shipping/np-ttn/{order_id}/status  # calls TrackingDocument/getStatusDocuments
```

---

## 3. Frontend — `DetailLogistics.tsx`

### 3.1 City dropdown uses `absolute` positioning without a `relative` parent
**Severity: High (broken UI)**

```tsx
<div className="mt-1 max-h-32 overflow-y-auto rounded-lg border ... absolute w-[calc(100%-24px)]">
```

This `absolute` positioned dropdown will be positioned relative to the nearest ancestor with `position: relative` in the DOM tree — which, in a deeply nested form inside a card, is likely the modal or the page root. The dropdown will visually escape the city input and appear in a completely wrong position.

**Fix:** Wrap the city input and its dropdown in a `relative` container:

```tsx
<div className="relative">
  <Input ... />
  {cities && cities.length > 0 && cityQuery !== formData.shipping_city && (
    <div className="absolute top-full left-0 mt-1 w-full z-[60] ...">
      ...
    </div>
  )}
</div>
```

---

### 3.2 No debounce on city search — fires NP API on every keystroke
**Severity: Medium**

The `cityQuery` state is updated on every `onChange` event and passed directly to `useSearchCities`. Although the hook has `enabled: query.length >= 2`, a user typing "Київ" still triggers 3 separate API calls (`"Ки"`, `"Киї"`, `"Київ"`).

**Fix:** Add a debounce of 300–400ms inside `useSearchCities`, or debounce the state update in the component:

```typescript
// In useShipping.ts
export function useSearchCities(query: string) {
  const [debouncedQuery, setDebouncedQuery] = useState(query);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 350);
    return () => clearTimeout(timer);
  }, [query]);
  
  return useQuery({
    queryKey: ['shipping', 'cities', debouncedQuery],
    queryFn: () => shippingApi.searchCities(debouncedQuery),
    enabled: debouncedQuery.length >= 2,
    staleTime: 1000 * 60 * 60,
  });
}
```

---

### 3.3 No click-outside handler for the city dropdown
**Severity: Medium**

The warehouse dropdown closes on `onBlur` (with a 200ms delay to allow clicks). The city dropdown has no such mechanism — it only closes when a city is selected. If the user opens the dropdown, then clicks somewhere else on the form without selecting a city, the dropdown remains open indefinitely.

**Fix:** Add an `onBlur` handler matching the warehouse pattern, or use a `useClickOutside` hook targeting the dropdown container.

---

### 3.4 City name / `shipping_city_ref` data inconsistency on save
**Severity: Medium (data integrity)**

If a user types a city name into the city field without selecting from the dropdown, `formData.shipping_city` will be a free-text string while `formData.shipping_city_ref` will still hold whatever value was set previously (either from the original order or from a previous selection).

For example:
- Order came from Shopify with `shipping_city = "Kyiv"`, `shipping_city_ref = null`
- User enters edit mode, types "Харків" but doesn't select from dropdown
- Saves → `shipping_city = "Харків"`, but `shipping_city_ref = null` or stale

On the next TTN creation, the validation in Section 2.1 will catch `null`, but a stale Ref is harder to detect.

**Fix:** Clear `shipping_city_ref` whenever the user modifies `cityQuery` after a selection has been made:

```tsx
onChange={e => {
  setCityQuery(e.target.value);
  // Invalidate the ref if user is typing again after selection
  if (formData.shipping_city_ref) {
    setFormData(p => ({ ...p, shipping_city_ref: '', shipping_warehouse_ref: '' }));
  }
}}
```

Also show the `shipping_city_ref` as a small verified badge or dim UUID next to the selected city in edit mode, so operators can see whether a valid Ref is selected.

---

### 3.5 TTN number card is `cursor-pointer` but has no click handler
**Severity: Low (UX)**

```tsx
<div className="... cursor-pointer group">
  <p className="font-mono text-base text-teal-100 font-black">{order.ttn_number}</p>
</div>
```

The cursor promises interactivity. The user naturally expects to click the TTN to copy it to clipboard or open NP tracking. Currently nothing happens.

**Fix:** Add a copy-to-clipboard action and an optional link to NP tracking:

```tsx
onClick={() => {
  navigator.clipboard.writeText(order.ttn_number);
  toast({ description: "TTN copied to clipboard" });
}}
```

Link template: `https://novaposhta.ua/tracking/?cargo_number={order.ttn_number}`

---

## 4. Frontend — `useShipping.ts`

### 4.1 Error state not surfaced from hooks
**Severity: Medium**

The `useSearchCities` and `useGetWarehouses` hooks expose `data` and `isLoading`, but the `error` property from React Query is discarded. If the NP API is down or the backend returns a 400 error, the dropdown will simply show nothing with no explanation.

**Fix:** Return and consume the `error` state in consuming components:

```typescript
export function useSearchCities(query: string) {
  return useQuery({
    // ...
    retry: 1,  // NP city search doesn't need 3 retries
  });
  // consumers: const { data, isLoading, error } = useSearchCities(q);
}
```

In `DetailLogistics.tsx`, display an inline error message below the city input when `error` is non-null.

---

### 4.2 `useCreateTTN` does not expose error state to the UI
**Severity: Medium**

```typescript
export function useCreateTTN() {
  return useMutation({ ... });
}
```

The mutation result includes `error` and `isError`, but the calling component (`onGenerateTTN`) has no way to display what went wrong. The user clicks "Generate NP Label", sees a spinner, and if the backend returns `400: "Sender city or warehouse not configured"`, they get no feedback.

**Fix:** In the parent component that calls `useCreateTTN`, consume `mutation.error` and display a toast or inline error:

```typescript
const ttnMutation = useCreateTTN();

const handleGenerateTTN = async () => {
  ttnMutation.mutate({ orderId, data: {} }, {
    onError: (err) => toast({ title: "TTN Error", description: err.message, variant: "destructive" }),
    onSuccess: () => toast({ description: "TTN created successfully" }),
  });
};
```

---

## 5. NP API — Correctness & Best Practices

### 5.1 Model name for TTN creation
The code uses `modelName: "InternetDocument"` with `calledMethod: "save"`. This is **correct** per the NP v2 API. The alternative `"InternetDocumentGeneral"` also works but is the same endpoint and is used for bulk creation. No change needed.

### 5.2 Phone number format
The code strips `+`, spaces, and hyphens. The NP API expects `380XXXXXXXXX` (12 digits, no plus, no spaces). The current normalization is correct but does not validate length. Add a guard:

```python
if len(clean_phone) != 12 or not clean_phone.startswith("380"):
    raise HTTPException(status_code=400, detail=f"Invalid phone format: {clean_phone}. Expected 380XXXXXXXXX")
```

### 5.3 `Cost` field — declared value vs COD amount
`Cost` in the NP payload is the **declared value** of the parcel for insurance purposes, not the COD collection amount. These are two different things. `Cost` should be the order value in UAH as an integer (NP does not accept decimal values). Use `int(order.total_price)` and ensure `total_price` is stored in UAH, not kopecks.

### 5.4 `SeatsAmount` is always `"1"` — no multi-parcel support
Hardcoding `SeatsAmount: "1"` is fine for MVP. Document this limitation and add it to the `CreateTTNRequest` body for future use.

### 5.5 `DateTime` — should use Kyiv timezone, not server UTC
```python
"DateTime": datetime.now().strftime("%d.%m.%Y"),
```
If the server runs in UTC (standard for Docker containers), and the current time is after 21:00 UTC in summer, `datetime.now()` will return the next calendar day compared to what the Kyiv operator sees. NP only allows TTN creation for today's date or future dates, so this could result in TTNs dated tomorrow appearing in the NP office today.

**Fix:**
```python
from zoneinfo import ZoneInfo
kyiv_tz = ZoneInfo("Europe/Kiev")
"DateTime": datetime.now(tz=kyiv_tz).strftime("%d.%m.%Y"),
```

---

## 6. Summary — Priority Matrix

| # | Issue | Severity | File | Action |
|---|-------|----------|------|--------|
| 2.1 | Missing city_ref / warehouse_ref validation | Critical | shipping.py | Add guards before payload |
| 2.2 | `db.flush()` instead of `db.commit()` | Critical | shipping.py | Replace with `await db.commit()` |
| 1.2 | Retry catches all exceptions incl. NP errors | High | nova_poshta.py | Custom exception, narrow retry |
| 2.4 | VolumeGeneral "0.001" too small | High | shipping.py | Use 0.004 default, make configurable |
| 2.5 | PaymentMethod/PayerType hardcoded | High | shipping.py | Add to shop settings |
| 2.6 | No COD support (BackwardDeliveryData) | High | shipping.py | Add to request model + payload |
| 3.1 | City dropdown absolute without relative parent | High | DetailLogistics.tsx | Wrap in relative div |
| 1.1 | Dead code `build_ttn_payload` with wrong field types | High | nova_poshta.py | Delete entirely |
| 2.3 | 5 sequential API calls, no sender caching | Medium | shipping.py | Cache sender Ref in shop model |
| 2.7 | No atomic TTN/DB handling | Medium | shipping.py | Log TTN before commit, add manual recovery |
| 3.2 | No debounce on city search | Medium | useShipping.ts | Add 350ms debounce |
| 3.3 | No click-outside for city dropdown | Medium | DetailLogistics.tsx | Add onBlur or useClickOutside |
| 3.4 | City text / city_ref inconsistency | Medium | DetailLogistics.tsx | Clear ref on manual typing |
| 4.1 | Error not surfaced from shipping hooks | Medium | useShipping.ts | Return and consume error |
| 4.2 | useCreateTTN error not shown to user | Medium | useShipping.ts | Add onError toast |
| 5.5 | DateTime uses server UTC not Kyiv tz | Medium | shipping.py | Use ZoneInfo("Europe/Kiev") |
| 1.3 | New httpx client per request | Medium | nova_poshta.py | Share client instance |
| 2.8 | No TTN delete / status tracking | Medium | shipping.py | Add two endpoints |
| 3.5 | TTN card cursor-pointer but no handler | Low | DetailLogistics.tsx | Add copy-to-clipboard |
| 1.4 | Unused `get_counterparty_addresses` | Low | nova_poshta.py | Remove dead method |

---

## 7. Suggested Agent Prompt

The following can be used directly as a task prompt for a coding agent:

---

**Task: Fix Nova Poshta TTN Integration in OrderHub CRM**

Fix the following issues in priority order across these files:
`backend/routers/shipping.py`, `backend/services/nova_poshta.py`, `frontend/src/hooks/useShipping.ts`, `frontend/src/components/orders/detail/DetailLogistics.tsx`

**P0 — Blockers (must fix first):**

1. In `shipping.py` `create_np_ttn`: add validation that `order.shipping_city_ref` and `order.shipping_warehouse_ref` are not None before building the payload. Raise HTTP 400 with a user-readable message if either is missing.

2. In `shipping.py` `create_np_ttn`: change `await db.flush()` to `await db.commit()` followed by `await db.refresh(order)` to ensure the TTN number is actually persisted.

3. In `nova_poshta.py`: delete the `build_ttn_payload` function at the bottom of the file — it is unused dead code with incorrect field types (passes string names where UUID Refs are required).

**P1 — Critical improvements:**

4. In `nova_poshta.py`: create a `NovaPoshtaAPIError(Exception)` class. In `_post`, raise `NovaPoshtaAPIError` (not `Exception`) when `data.get("success") == False`. Update the retry decorator to only retry on `httpx.HTTPError`, not on `NovaPoshtaAPIError`.

5. In `shipping.py`: add Ukraine/Kyiv timezone to the DateTime field: `from zoneinfo import ZoneInfo; datetime.now(tz=ZoneInfo("Europe/Kiev")).strftime("%d.%m.%Y")`.

6. In `shipping.py` `CreateTTNRequest`: add `cash_on_delivery: bool = False` and `cod_amount: float | None = None`. When `cash_on_delivery` is True, append `BackwardDeliveryData` to the payload: `[{"PayerType": "Recipient", "CargoType": "Money", "RedeliveryString": str(int(cod_amount or order.total_price))}]`.

7. In `shipping.py`: change `VolumeGeneral` default from `"0.001"` to `str(shop.np_default_volume_m3 or 0.004)`.

8. In `shipping.py`: replace hardcoded `"PayerType": "Sender"` and `"PaymentMethod": "Cash"` with shop-level settings: `shop.np_default_payer_type or "Sender"` and `shop.np_default_payment_method or "Cash"`. Add these two fields to the Shop model migration.

**P2 — Frontend:**

9. In `DetailLogistics.tsx`: wrap the city `<Input>` and its dropdown `<div>` in a `<div className="relative">` container so the `absolute`-positioned dropdown is correctly anchored.

10. In `DetailLogistics.tsx`: when the user modifies `cityQuery` after a city has been selected (`formData.shipping_city_ref` is non-empty), clear `shipping_city_ref` and `shipping_warehouse_ref` in the form state, forcing the user to re-select from the dropdown.

11. In `useShipping.ts` `useSearchCities`: add a 350ms debounce before the query is used as the React Query key, to avoid firing on every keystroke.

12. In `DetailLogistics.tsx`: add `onClick={() => navigator.clipboard.writeText(order.ttn_number)}` to the TTN display card, and show a brief "Copied!" confirmation (toast or inline text).

13. In the component that calls `useCreateTTN` (parent of `DetailLogistics`): add an `onError` callback to the `mutate` call that displays a user-visible error message with the error detail from the backend.

**P3 — Technical debt:**

14. In `nova_poshta.py`: remove the unused `get_counterparty_addresses` method.

15. In `shipping.py`: after resolving `sender_ref` and `sender_contact_ref`, store them back on the `shop` model (`shop.np_sender_ref`, `shop.np_sender_contact_ref`, `shop.np_sender_phone`) and skip the two `get_counterparties`/`get_contact_persons` calls on subsequent TTN creations if these fields are already populated.

16. Add a `DELETE /api/shipping/np-ttn/{order_id}` endpoint that calls `NovaPoshtaClient._post("InternetDocument", "delete", {"DocumentRefs": [order.ttn_ref]})` and clears `order.ttn_number` in the DB.

---
