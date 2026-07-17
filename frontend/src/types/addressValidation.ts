/**
 * OrderHub CRM — Address validation types (ADDR-VAL-1)
 *
 * Hand-written mirror of backend/schemas/address_validation.py and
 * backend/schemas/app_setting.py. Per the project convention we use manual
 * TypeScript types rather than codegen — keep this file in sync with the Pydantic
 * schemas. Drift risk is documented in CLAUDE.md.
 */

/** Mirrors models.order.AddressValidationStatus. */
export type AddressValidationStatus =
  | 'verified'
  | 'needs_attention'
  | 'couldnt_verify'
  | 'unsupported'
  | 'ua'
  | 'unavailable';

export interface AddressComponents {
  street_1: string | null;
  street_2: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  country: string | null;
}

export interface AddressFieldDiff {
  field: string;
  original: string | null;
  suggested: string | null;
}

export interface AddressVerdict {
  status: AddressValidationStatus;
  message: string | null;
  formatted_address: string | null;
  components: AddressComponents | null;
  diff: AddressFieldDiff[];
  validated_at: string | null;
}

/** Masked status of a stored global API key. Never carries the plaintext. */
export interface ApiKeyStatus {
  is_set: boolean;
  last4: string | null;
  updated_at: string | null;
}
