import { countryName } from '../countries';

describe('countryName (CTRY-1)', () => {
  it('resolves a known ISO-2 code to its full English name', () => {
    expect(countryName('GB')).toBe('United Kingdom');
    expect(countryName('UA')).toBe('Ukraine');
    expect(countryName('US')).toBe('United States');
  });

  it('accepts lower-case and padded input', () => {
    expect(countryName('gb')).toBe('United Kingdom');
    expect(countryName(' ua ')).toBe('Ukraine');
  });

  it('returns the raw upper-cased code when it cannot be resolved', () => {
    // Bad data must stay visible rather than read as "missing".
    // QQ is unassigned in ISO-3166 — Intl falls back to the code itself.
    // (ZZ is *not* a good example: ICU defines it as "Unknown Region".)
    expect(countryName('QQ')).toBe('QQ');
    expect(countryName('usa')).toBe('USA');
  });

  it('returns the fallback for empty input', () => {
    expect(countryName(null)).toBe('—');
    expect(countryName(undefined)).toBe('—');
    expect(countryName('')).toBe('—');
  });

  it('honours each call site’s own fallback text', () => {
    expect(countryName(null, 'N/A')).toBe('N/A');
    expect(countryName(null, 'Global')).toBe('Global');
    expect(countryName('', '??')).toBe('??');
  });
});
