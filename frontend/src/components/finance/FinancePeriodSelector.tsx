import { useEffect, useMemo, useState } from 'react';
import { format } from 'date-fns';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  PRESETS,
  PRESET_STORAGE_KEY,
  loadLastPreset,
  rangeForPreset,
  type PeriodRange,
  type PresetKey,
} from './periodPresets';

interface FinancePeriodSelectorProps {
  value: PeriodRange;
  onChange: (range: PeriodRange, preset: PresetKey) => void;
}

export default function FinancePeriodSelector({ value, onChange }: FinancePeriodSelectorProps) {
  const [preset, setPreset] = useState<PresetKey>(() => loadLastPreset());
  const [customStart, setCustomStart] = useState<string>(format(value.start, 'yyyy-MM-dd'));
  const [customEnd, setCustomEnd] = useState<string>(format(value.end, 'yyyy-MM-dd'));

  useEffect(() => {
    try {
      localStorage.setItem(PRESET_STORAGE_KEY, preset);
    } catch {
      // ignore
    }
  }, [preset]);

  const handlePreset = (key: PresetKey) => {
    setPreset(key);
    if (key === 'custom') {
      const range: PeriodRange = {
        start: new Date(customStart),
        end: new Date(customEnd),
      };
      onChange(range, key);
    } else {
      const range = rangeForPreset(key);
      setCustomStart(format(range.start, 'yyyy-MM-dd'));
      setCustomEnd(format(range.end, 'yyyy-MM-dd'));
      onChange(range, key);
    }
  };

  const handleCustomApply = () => {
    const start = new Date(customStart);
    const end = new Date(customEnd);
    if (start > end) return;
    onChange({ start, end }, 'custom');
  };

  const summary = useMemo(
    () => `${format(value.start, 'MMM d, yyyy')} → ${format(value.end, 'MMM d, yyyy')}`,
    [value.start, value.end],
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {PRESETS.map((p) => (
          <Button
            key={p.key}
            type="button"
            variant="ghost"
            size="sm"
            className={cn(
              'border text-xs font-semibold',
              preset === p.key
                ? 'border-teal-500/40 bg-teal-500/10 text-teal-300'
                : 'border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100',
            )}
            onClick={() => handlePreset(p.key)}
          >
            {p.label}
          </Button>
        ))}
        <span className="ml-2 text-[11px] uppercase tracking-wider text-zinc-400 font-medium">
          {summary}
        </span>
      </div>

      {preset === 'custom' && (
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
              From
            </label>
            <Input
              type="date"
              value={customStart}
              onChange={(e) => setCustomStart(e.target.value)}
              className="border-zinc-800 bg-zinc-900/50 h-9 w-44"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
              To
            </label>
            <Input
              type="date"
              value={customEnd}
              onChange={(e) => setCustomEnd(e.target.value)}
              className="border-zinc-800 bg-zinc-900/50 h-9 w-44"
            />
          </div>
          <Button
            type="button"
            size="sm"
            className="bg-teal-600 hover:bg-teal-500 text-white"
            onClick={handleCustomApply}
          >
            Apply
          </Button>
        </div>
      )}
    </div>
  );
}
