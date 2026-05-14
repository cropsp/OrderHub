import {
  endOfMonth,
  endOfWeek,
  endOfYear,
  startOfMonth,
  startOfWeek,
  startOfYear,
  subMonths,
} from 'date-fns';

export type PresetKey =
  | 'today'
  | 'this_week'
  | 'this_month'
  | 'last_month'
  | 'this_year'
  | 'custom';

export interface PeriodRange {
  start: Date;
  end: Date;
}

export const PRESETS: { key: PresetKey; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: 'this_week', label: 'This Week' },
  { key: 'this_month', label: 'This Month' },
  { key: 'last_month', label: 'Last Month' },
  { key: 'this_year', label: 'This Year' },
  { key: 'custom', label: 'Custom' },
];

export const PRESET_STORAGE_KEY = 'orderhub:shopFinance:lastPreset';

export function rangeForPreset(preset: PresetKey, now: Date = new Date()): PeriodRange {
  switch (preset) {
    case 'today':
      return {
        start: new Date(now.getFullYear(), now.getMonth(), now.getDate()),
        end: new Date(now.getFullYear(), now.getMonth(), now.getDate()),
      };
    case 'this_week':
      return {
        start: startOfWeek(now, { weekStartsOn: 1 }),
        end: endOfWeek(now, { weekStartsOn: 1 }),
      };
    case 'this_month':
      return { start: startOfMonth(now), end: endOfMonth(now) };
    case 'last_month': {
      const prev = subMonths(now, 1);
      return { start: startOfMonth(prev), end: endOfMonth(prev) };
    }
    case 'this_year':
      return { start: startOfYear(now), end: endOfYear(now) };
    case 'custom':
      return { start: startOfMonth(now), end: endOfMonth(now) };
  }
}

export function loadLastPreset(): PresetKey {
  try {
    const raw = localStorage.getItem(PRESET_STORAGE_KEY);
    if (raw && PRESETS.some((p) => p.key === raw)) {
      return raw as PresetKey;
    }
  } catch {
    // ignore
  }
  return 'this_month';
}
