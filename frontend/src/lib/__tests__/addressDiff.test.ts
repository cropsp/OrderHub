import { describe, expect, it } from 'vitest';

import { isCosmeticFieldDiff, normalizeStreet, partitionDiff } from '../addressDiff';
import type { AddressFieldDiff } from '@/types/addressValidation';

const diff = (field: string, original: string, suggested: string): AddressFieldDiff => ({
  field, original, suggested,
});

describe('addressDiff — cosmetic vs actionable (OQ-3)', () => {
  it('treats a zip+4 suffix as cosmetic', () => {
    expect(isCosmeticFieldDiff(diff('zip', '02141', '02141-1970'))).toBe(true);
  });

  it('treats a changed base zip as actionable', () => {
    expect(isCosmeticFieldDiff(diff('zip', '02141', '02150'))).toBe(false);
  });

  it('treats a street-suffix abbreviation as cosmetic', () => {
    expect(isCosmeticFieldDiff(diff('street_1', '1600 Pennsylvania Avenue NW', '1600 Pennsylvania Ave NW'))).toBe(true);
    expect(isCosmeticFieldDiff(diff('street_1', '4 Chemin de Chaponval', '4 Chem. de Chaponval'))).toBe(true);
  });

  it('treats a changed house number as actionable (digits survive normalisation)', () => {
    expect(isCosmeticFieldDiff(diff('street_1', '1600 Pennsylvania Ave', '1601 Pennsylvania Ave'))).toBe(false);
  });

  it('always surfaces a city or state change', () => {
    expect(isCosmeticFieldDiff(diff('city', 'Redbridge, London', 'London'))).toBe(false);
    expect(isCosmeticFieldDiff(diff('state', 'CA', 'California'))).toBe(false);
  });

  it('normalizeStreet canonicalises abbreviations and whitespace', () => {
    expect(normalizeStreet('1600 Pennsylvania Avenue NW')).toBe(normalizeStreet('1600  Pennsylvania Ave. NW'));
  });

  it('partitions a mixed diff — a real city change is actionable, the zip+4 is cosmetic', () => {
    const { actionable, cosmetic } = partitionDiff([
      diff('city', 'Redbridge, London', 'London'),
      diff('zip', '02141', '02141-1970'),
    ]);
    expect(actionable.map((d) => d.field)).toEqual(['city']);
    expect(cosmetic.map((d) => d.field)).toEqual(['zip']);
  });

  it('partitions an all-cosmetic diff with no actionable entries', () => {
    const { actionable, cosmetic } = partitionDiff([
      diff('street_1', '1600 Pennsylvania Avenue NW', '1600 Pennsylvania Ave NW'),
      diff('zip', '20500', '20500-0005'),
    ]);
    expect(actionable).toHaveLength(0);
    expect(cosmetic).toHaveLength(2);
  });
});
