/**
 * Country display helper (CTRY-1).
 *
 * Country is stored as an ISO-3166-1 alpha-2 code (`String(2)`) and the code is
 * what every piece of business logic keys on — most notably the Nova Poshta vs
 * international branch in DetailLogistics (`shipping_country === 'UA'`). This
 * helper is display-only: it never changes what is stored, entered, or compared.
 *
 * Names come from the runtime's built-in `Intl.DisplayNames`, so there is no
 * hardcoded country list to maintain and no new dependency.
 */

/** Constructed once — building an Intl formatter per render is wasteful. */
const REGION_NAMES = new Intl.DisplayNames(['en'], { type: 'region' });

/**
 * Full English country name for an ISO-3166-1 alpha-2 code.
 *
 * Empty/null → `fallback` (each call site keeps its own existing empty text).
 * An unknown or malformed code returns the raw upper-cased code rather than the
 * fallback, so bad data stays visible instead of silently reading as "missing".
 */
export function countryName(code?: string | null, fallback = '—'): string {
  if (!code) return fallback;
  const cc = code.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(cc)) return code.toUpperCase();
  try {
    return REGION_NAMES.of(cc) ?? cc;
  } catch {
    return cc;
  }
}
