# Parcel-watchlist research — carrier APIs, hold periods, aggregators

**Date:** 2026-08-26. Three Opus web-research agents, findings verified against primary sources on that day.
**Consumers:** future `UKRP-TRACK-1`, `HOLD-1`, `STAGE-1` sprints (see `order-cases-plan.md` §6 for sequencing). Prices/policies drift — re-verify anything load-bearing before building on it.

## 1. Ukrposhta StatusTracking API

- **Official API exists and is current.** Canonical spec: [Status-tracking-API-04032026.pdf](https://dev.ukrposhta.ua/uploads/Status-tracking-API-04032026.pdf) (UA edition; the EN one is a year stale). Base URL `https://www.ukrposhta.ua/status-tracking/0.0.1` (keep the `www.`).
- **Returns FULL event history** per barcode — unlike NP's keyless API (current-status-only, the whole WB-TRACK-EVENT-COMPLETENESS problem). Batch: 50 (full history) / 100 (last status). **Use the `/with-not-found` variants** (`POST /statuses/with-not-found`, `POST /statuses/last/with-not-found`) — the plain endpoints have a documented history of one dead barcode poisoning a batch.
- **Auth:** `Authorization: Bearer {uuid}` — a **separate StatusTracking key**, not the eCom key; issued only by the assigned account manager under the existing contract. No self-service portal, no published fee (likely free, unverified), no published SLA/rate limit. Support: api-support@ukrposhta.ua.
- **Event dictionary:** Appendix Б of the spec PDF — the only place it exists. Key terminal codes: `41000` delivered (**but `41000` + `eventReason_id == 10` = delivered back to SENDER, i.e. a return** — `41010` is synthetic and never on the wire; `31200` in history corroborates a return), `48000` delivered abroad, `10600/10602/10603` cancelled.
- **Parsing traps:** `step` is NOT monotonic with `date` — sort by `date`; `event` is sometimes int, sometimes string — coerce; container-level codes `2100/2200/2201/3006/4001/4014–4082` (PREDES/RESDES/CARDIT) are receptacle scans, **not item progress** — a stall detector anchored on them emits permanent false alarms.
- **International coverage is structurally limited:** abroad events depend on the foreign operator's UPU EDI feed. UPU allows up to **120 h** to transmit an event and targets only **80%** carriage of delivery/attempt events. Canada/Australia/Norway send no tracking for non-PRIME small packets — last status will be "processing started in destination country", forever. **Ask the manager what product the `LP` prefix is** (PRIME or not) — it decides expected coverage. GTT retention: 30 days undelivered / 5 days post-delivery.
- **Polling:** at our volume, 2 requests per cycle; daily cadence is enough for international (matches keyCRM practice; more buys nothing against 120 h latency). Scraping the site is contractually prohibited (Порядок §6.2.3).

## 2. Hold-for-pickup / return-to-sender periods (verified official policy)

For the `HOLD-1` config table. **Clock-start and day-type vary — a one-day error kills the feature.**

| Carrier | Hold | Day type | Clock starts | Reminder | Extendable | Source |
|---|---|---|---|---|---|---|
| Canada Post | **15 d** | calendar | day after notice | Final Notice at day 5 | — | [canadapost delivery options, fn.2](https://www.canadapost-postescanada.ca/cpc/en/support/articles/parcel-services-shipping-in-canada/delivery-options.page) |
| USPS | **15 d** (use); 30 d IMM upper bound — officially unreconciled | calendar | notice (PS 3849) | redelivery bookable | no | [DMM 508.1.1.7](https://pe.usps.com/text/dmm300/508.htm), [IMM 766](https://pe.usps.com/text/imm/immc7_023.htm) |
| Poczta Polska | **14 d** total | calendar | day after FIRST notice (second notice after day 7 — don't count 7) | yes | paid, max +14 d | [Regulamin 01-02-2026](https://www.poczta-polska.pl/wp-content/uploads/2024/12/regulaminu-swiadczenia-uslug-powszechnych-01-02-2026_www.pdf) |
| Deutsche Post (Filiale, letter-post = LP…UA case) | **7 working days** (Mon–Sat, excl. DE holidays) | business | day after notice | — | no | [DP Benachrichtigung](https://www.deutschepost.de/de/hilfe-kundenservice/empfangen/benachrichtigung.html) |
| DHL Packstation | 7–9 d, but **UA parcels can't route there** (non-EU excluded) — moot | — | — | — | no (explicit) | [DHL Packstation help](https://www.dhl.de/en/privatkunden/hilfe-kundenservice/packstation/empfangen.html) |
| Royal Mail | **18 d** (auto next-day redelivery now default, so hold often never starts) | calendar | — | — | free redelivery | [royalmail.com/redelivery](https://www.royalmail.com/receiving-mail/redelivery) |
| La Poste | **15 d** | calendar | day after avis | — | proxy pickup only | [aide.laposte.fr](https://aide.laposte.fr/contenu/comment-et-sous-quel-delai-puis-je-recuperer-mes-lettres-recommandees-et-colissimo-en-point-de-retrait-postal) |
| Australia Post | **10 business days** | business | — | — | transfer A$7.20 | [auspost missed deliveries](https://auspost.com.au/receiving/parcel-deliveries/missed-parcel-deliveries) |
| NovaPost USA (own arm) | 2 attempts → warehouse; branch hold **7 d**, then RTS **without prior notice** | calendar | notification | SMS/email/app | postpone ≤5 bus. days | [novapost.com US offer, Art. 4.7.2(b)](https://novapost.com/en-us/more/offer/) |
| GoFo Express US | **no published US policy** (FR entity: 3 attempts, 14 d — do NOT assume it transfers) | — | — | — | — | gofo.com/fr FAQ only |

InPost Paczkomat (48 h) is irrelevant for LP…UA (delivered by Poczta Polska), but if a commercial carrier ever routes PL last-mile there, that window deserves its own alert tier.

## 3. Tracking aggregators — evaluated, not buying (for now)

Coverage is NOT a differentiator: 17TRACK, AfterShip, TrackingMore, Ship24, ParcelsApp all list Nova Poshta Global, Ukrposhta and GOFO. Pricing at 100–300/mo: 17TRACK ~$10/mo equivalent ($119/yr per 5k pack, webhooks on all tiers); ParcelsApp $19/mo per 300; Ship24 $59/mo (API is Pro-only); AfterShip $59+/mo (API Premium-gated, **multi-leg tracking Enterprise-only — non-Enterprise is documented first-mile-only**; avoid for this use case).

**The decisive finding:** aggregators discover the US last-mile number **from the first-mile carrier's own feed** — the same NP feed we already poll free, which (per the Rick Felix appendix data) already passes through GoFo depot scans. So the marginal value for NP parcels is likely ~zero. What they genuinely add: a ready-made normalized taxonomy and webhooks-instead-of-polling.

**Decision path (agreed):** don't buy. If evidence is wanted before UKRP-TRACK-1: free diff test — register ~10 already-delivered NP numbers on 17TRACK's free quota, diff their event lists against our `wb_tracking_event` mirror. Non-empty diff ⇒ reconsider 17TRACK. For our own stage normalisation, model on **Ship24's three-field design** (`statusMilestone` 8 values / `statusCategory` 6 / `statusCode` ~20 — [docs.ship24.com/status](https://docs.ship24.com/status/)) — the cleanest of the four to reimplement.

## 4. Unverified / open items

- Ukrposhta StatusTracking key fee, rate limit, issuance turnaround — ask the manager.
- `LP` prefix product (PRIME?) — decides destination-leg visibility per lane.
- USPS 15-vs-30 day reconciliation — none exists; countdown on 15.
- GoFo US hold policy — nothing published; treat countdown as unknown for that leg (or use NovaPost US 7 d only when the parcel moves under NovaPost's own contract).
- 17TRACK free-quota policy post-2026-01-07 (100/mo vs one-time 200) — confirm at signup if the diff test happens.
