/**
 * OrderHub CRM — FX settings types (FX-CONVERSION)
 *
 * Hand-written mirror of backend/schemas/fx.py. There is no codegen here — if the
 * Pydantic field names or types change, update this file too.
 *
 * Every rate is `uah_per_usd`: UAH per 1 USD, as published by NBU. Converting a
 * UAH cost into USD therefore DIVIDES by it. Numbers arrive as strings because
 * they are Decimals server-side — parse before arithmetic, never rely on JSON
 * numbers for money-adjacent values.
 */

export type FxRateSource = 'manual' | 'nbu';

export interface FxSettings {
  /** What conversions actually use: override if set, else cached, else null. */
  uah_per_usd_effective: string | null;
  source: FxRateSource | null;
  uah_per_usd_override: string | null;
  uah_per_usd_cached: string | null;
  /** NBU's exchangedate for the cached rate — the banking day it is FOR, which
   *  runs one day ahead of the fetch. */
  rate_date: string | null;
  fetched_at: string | null;
  is_stale: boolean;
  source_url: string;
}

export interface FxSettingsUpdate {
  source_url?: string;
  uah_per_usd_override?: string;
}
