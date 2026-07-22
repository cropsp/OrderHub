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
