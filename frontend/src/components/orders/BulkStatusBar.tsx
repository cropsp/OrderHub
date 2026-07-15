import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ORDER_STATUS, statusLabel } from '@/lib/order-status';
import type { OrderStatusValue } from '@/lib/order-status';

interface BulkStatusBarProps {
  count: number;
  onClear: () => void;
  onApply: (status: OrderStatusValue) => void;
}

export default function BulkStatusBar({ count, onClear, onApply }: BulkStatusBarProps) {
  const [status, setStatus] = useState<OrderStatusValue | ''>('');

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 mb-3 rounded-xl border border-teal-500/20 bg-teal-500/5">
      <p className="text-[11px] font-bold text-teal-300 uppercase tracking-widest">
        {count} selected
      </p>

      <div className="flex items-center gap-2">
        <Select value={status} onValueChange={(val) => setStatus(val as OrderStatusValue)}>
          <SelectTrigger className="w-[180px] h-9 rounded-xl border-zinc-800 bg-zinc-900 text-zinc-300">
            <SelectValue placeholder="Set status to..." />
          </SelectTrigger>
          <SelectContent className="bg-zinc-900 border-zinc-800 text-zinc-300">
            {Object.values(ORDER_STATUS).map((value) => (
              <SelectItem
                key={value}
                value={value}
                className="focus:bg-zinc-800 focus:text-zinc-100"
              >
                {statusLabel(value)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          size="sm"
          disabled={!status}
          onClick={() => status && onApply(status)}
          className="h-9 px-4 bg-teal-500 hover:bg-teal-400 text-zinc-950 font-bold rounded-xl uppercase text-[10px] tracking-widest border-none disabled:opacity-40"
        >
          Apply
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClear}
          className="h-9 px-4 border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl font-bold uppercase text-[10px] tracking-widest"
        >
          Clear
        </Button>
      </div>
    </div>
  );
}
