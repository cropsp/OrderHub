import { format } from 'date-fns';

/**
 * Shared display formatters (Wave A).
 *
 * Dates render in uk-UA numeric style (dd.MM.yyyy) app-wide — the business is
 * Ukrainian and the daily operators are in Kyiv. Money renders with 2 decimals
 * and en-US digit grouping (1,234.50); the currency code is left to the caller
 * so existing styled `<span>{currency}</span>` markup is preserved.
 */

type DateInput = string | number | Date | null | undefined;

const EM_DASH = '—';

function toDate(input: DateInput): Date | null {
  if (input == null || input === '') return null;
  const d = input instanceof Date ? input : new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** dd.MM.yyyy — em-dash when the date is missing/invalid. */
export function formatDate(input: DateInput): string {
  const d = toDate(input);
  return d ? format(d, 'dd.MM.yyyy') : EM_DASH;
}

/** dd.MM.yyyy HH:mm — em-dash when the date is missing/invalid. */
export function formatDateTime(input: DateInput): string {
  const d = toDate(input);
  return d ? format(d, 'dd.MM.yyyy HH:mm') : EM_DASH;
}

/**
 * An elapsed-day count as "12.6d" (WB-TRACK-2).
 *
 * Display only. The number itself is always computed server-side — the delivery
 * monitor never subtracts dates, because "overdue" and "stalled" are defined
 * once in `wb_tracking_service` and shared with the MCP tool.
 */
export function formatDays(days: number | null | undefined): string {
  if (days == null || !Number.isFinite(days)) return EM_DASH;
  return `${days.toFixed(1)}d`;
}

/** MM.yyyy — numeric month/year, em-dash when missing/invalid. */
export function formatMonthYear(input: DateInput): string {
  const d = toDate(input);
  return d ? format(d, 'MM.yyyy') : EM_DASH;
}

/**
 * 2-decimal money digits with en-US grouping (e.g. 1,234.50).
 * Accepts a string too — the API serialises Decimal money fields as strings.
 * Returns an em-dash for null/undefined/empty/non-finite input so absent totals
 * read honestly instead of "0.00". The currency code is rendered by the caller.
 */
export function formatMoney(amount: number | string | null | undefined): string {
  if (amount == null || amount === '') return EM_DASH;
  const n = Number(amount);
  if (!Number.isFinite(n)) return EM_DASH;
  return n.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
