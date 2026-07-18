/**
 * OrderHub CRM — Address diff classification (ADDR-VAL-2, OQ-3)
 *
 * Splits Google's original→suggested diff into *actionable* changes (a real
 * delivery difference: city, state, street number, base zip) and *cosmetic* ones
 * (a zip+4 suffix or a street-type abbreviation like "Avenue"→"Ave"). Only when
 * EVERY entry is cosmetic do we de-emphasise the diff, so a `verified` address does
 * not nag. The predicate is deliberately conservative: an unrecognised change is
 * treated as actionable, so it can only ever over-surface, never hide a real change.
 */
import type { AddressFieldDiff } from '@/types/addressValidation';

/** Street-type words that Google may abbreviate. Curated (US + the FR "Chem." seen
 *  on prod); anything not here simply isn't treated as cosmetic. Each row is a set of
 *  equivalent spellings — members normalise to the row's first entry. */
const STREET_SUFFIX_GROUPS: string[][] = [
  ['avenue', 'ave'],
  ['street', 'st'],
  ['road', 'rd'],
  ['drive', 'dr'],
  ['boulevard', 'blvd'],
  ['lane', 'ln'],
  ['court', 'ct'],
  ['place', 'pl'],
  ['square', 'sq'],
  ['chemin', 'chem'],
];

const SUFFIX_CANONICAL: Record<string, string> = Object.fromEntries(
  STREET_SUFFIX_GROUPS.flatMap((group) => group.map((word) => [word, group[0]])),
);

/** Lowercase, strip punctuation, collapse whitespace, canonicalise street-type
 *  abbreviations. Digits (house numbers) are left untouched, so a differing street
 *  number never normalises equal. */
export function normalizeStreet(value: string | null): string {
  return (value ?? '')
    .toLowerCase()
    .replace(/[.,]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .map((token) => SUFFIX_CANONICAL[token] ?? token)
    .join(' ');
}

/** The base of a postal code — everything before the first hyphen. "02141-1970" → "02141". */
function baseZip(value: string | null): string {
  return (value ?? '').trim().split('-')[0];
}

/** True when this single field change is purely cosmetic (no delivery impact). */
export function isCosmeticFieldDiff(entry: AddressFieldDiff): boolean {
  switch (entry.field) {
    case 'zip':
      // Cosmetic only when the base zip is unchanged (a +4 suffix was added/removed).
      return baseZip(entry.original) === baseZip(entry.suggested);
    case 'street_1':
    case 'street_2':
      return normalizeStreet(entry.original) === normalizeStreet(entry.suggested);
    // city / state / country are always a real change.
    default:
      return false;
  }
}

export interface PartitionedDiff {
  actionable: AddressFieldDiff[];
  cosmetic: AddressFieldDiff[];
}

/** Split a verdict's diff into actionable vs cosmetic entries. When `actionable`
 *  is empty the caller should de-emphasise (a `verified`/formatting-only result). */
export function partitionDiff(diff: AddressFieldDiff[]): PartitionedDiff {
  const actionable: AddressFieldDiff[] = [];
  const cosmetic: AddressFieldDiff[] = [];
  for (const entry of diff) {
    (isCosmeticFieldDiff(entry) ? cosmetic : actionable).push(entry);
  }
  return { actionable, cosmetic };
}
