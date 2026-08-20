import type { PaginatedResponse } from './common'

/** Masked status of the WesternBid credential pair (WB-1). Never carries either
 *  plaintext — both the API key and login are secrets. */
export interface WesternBidCredentialsStatus {
  api_key_is_set: boolean
  api_key_last4: string | null
  login_is_set: boolean
  login_last4: string | null
  updated_at: string | null
}

/** Write-only payload for setting/replacing the WesternBid credentials. */
export interface WesternBidCredentialsUpdate {
  api_key: string
  login: string
}

/** One tracking entry WB reports per parcel — an object, not a bare string. */
export interface WbTrackingNumber {
  Identifier: string
  TrackingNumber: string
}

/** One mirrored WesternBid parcel. Status fields are raw strings — WB's value
 *  sets are undocumented and observed as-is this sprint. */
export interface WbParcel {
  shipment_id: string
  shipping_type: string | null
  carrier_type: string | null
  shipping_service_type: string | null
  tracking_numbers: WbTrackingNumber[]
  recipient_name: string | null
  recipient_postal_code: string | null
  recipient_country_code: string | null
  payment_status: string | null
  wb_status: string | null
  wb_created_at: string | null
  first_seen_at: string
  last_seen_at: string
}

export type WbParcelListResponse = PaginatedResponse<WbParcel>

/**
 * Delivery tracking (WB-TRACK-1 / WB-TRACK-2).
 *
 * Mirrors `backend/schemas/wb_tracking.py`. There is no codegen — if the
 * Pydantic models change, change these by hand.
 */

/** The server's own states, mirroring `wb_tracking_service.STATE_*`. */
export const PARCEL_STATES = [
  'delivered',
  'moving',
  'problem',
  'no_data',
  'untracked',
] as const

export type ParcelState = (typeof PARCEL_STATES)[number]

/**
 * Everything the monitor shows above the fold. Derived from PARCEL_STATES so a
 * state added server-side reaches the page instead of being silently dropped —
 * the delivered group is the exception because it is fetched separately.
 */
export const NON_DELIVERED_STATES = PARCEL_STATES.filter(
  (s) => s !== 'delivered',
)

/**
 * One parcel as the server classified it. Every attention signal
 * (`state`, `is_overdue`, `is_stalled`) and every elapsed-day figure is
 * computed server-side and read verbatim here — the page never re-derives
 * "stuck" (WB-TRACK-1 rule 7).
 */
export interface TrackedParcel {
  tracking_number: string | null
  carrier: string | null
  shipment_id: string
  order_id: string | null
  order_number: string | null
  /** Every carrier number WB reported. The only handle on `untracked` rows,
   *  whose `tracking_number` (the Nova Poshta one) is always null. */
  tracking_numbers: WbTrackingNumber[]

  state: ParcelState
  status_code: string | null
  /** Nova Poshta's own Ukrainian wording, verbatim — never mapped. */
  status_text: string | null

  is_overdue: boolean
  is_stalled: boolean
  days_overdue: number | null
  days_since_movement: number | null

  recipient_name: string | null
  city_recipient: string | null
  recipient_country_code: string | null

  scheduled_delivery_at: string | null
  last_movement_at: string | null
  delivered_at: string | null
  no_data_since: string | null

  wb_status: string | null
  payment_status: string | null
  wb_created_at: string | null
}

/** Counts always describe the FULL set, even when `parcels` is filtered. */
export interface TrackingCounts {
  total: number
  delivered: number
  moving: number
  problem: number
  no_data: number
  untracked: number
  overdue: number
  stalled: number
}

export interface TrackingOverview {
  counts: TrackingCounts
  parcels: TrackedParcel[]
  /** Last time the poller touched any parcel. Null means it has never run. */
  polled_at: string | null
  stalled_days: number
}

/** One observed transition from `wb_tracking_event`, oldest first. */
export interface TrackingEvent {
  status_code: string | null
  status_text: string | null
  np_tracking_update_date: string | null
  observed_at: string
}

export interface TrackingRefreshResult {
  polled: number
  created: number
  changed: number
  delivered: number
  no_data: number
  missing: number
  polled_at: string | null
  /** WB-ALERTS-1: alert sync rides the same pass as the poll. */
  alerts_opened: number
  alerts_resolved: number
}

/**
 * Dashboard parcel alerts (WB-ALERTS-1).
 *
 * Mirrors `backend/schemas/wb_alert.py` — same hand-mirroring rule as above.
 */

/** Severity order, mirroring `wb_tracking_service.ALERT_KIND_ORDER`. */
export const PARCEL_ALERT_KINDS = [
  'delivery_problem',
  'no_data_stuck',
  'overdue_long',
  'untracked_aging',
] as const

export type ParcelAlertKind = (typeof PARCEL_ALERT_KINDS)[number]

export interface ParcelAlert {
  id: string
  /** A ParcelAlertKind in practice; typed loosely so a kind added server-side
   *  renders as an unstyled row rather than crashing the dashboard. */
  kind: string
  /** Short Ukrainian reason, as of the last poll that saw the condition. */
  detail: string
  shipment_id: string
  /** The Nova Poshta number — null on `untracked_aging`, where the carrier's
   *  own number in `tracking_numbers` is the only thing an operator can act on. */
  tracking_number: string | null
  tracking_numbers: WbTrackingNumber[]
  recipient_name: string | null
  carrier: string | null
  raised_at: string
  /** Days since the alert was raised. A plain number, never a Decimal-as-string
   *  (the WB-TRACK-2 lesson: `"10" < "5"`). */
  age_days: number
  dismissed_at: string | null
  dismissed_by_id: string | null
}

export interface ParcelAlertList {
  alerts: ParcelAlert[]
  /** When the alert set was last reconciled. null means the poll has never
   *  run — which must not be read as "nothing is wrong". */
  synced_at: string | null
}
