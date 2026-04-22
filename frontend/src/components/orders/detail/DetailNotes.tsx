import { useState, useEffect, useCallback } from 'react';
import { debounce } from 'lodash-es';
import { NotepadText, Sliders } from 'lucide-react';
import type { OrderDetail } from '@/types/order';

interface NoteProps {
  order: OrderDetail;
  onUpdate: (payload: any) => Promise<void>;
}

export function DetailCustomizationInfo({ order, onUpdate }: NoteProps) {
  const [val, setVal] = useState(order.custom_info || '');

  useEffect(() => {
    setVal(order.custom_info || '');
  }, [order.id, order.custom_info]);

  const debouncedSave = useCallback(
    debounce(async (v: string) => {
      await onUpdate({ custom_info: v });
    }, 1000),
    [onUpdate]
  );

  const handleChange = (v: string) => {
    setVal(v);
    debouncedSave(v);
  };

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4">
      <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-3 px-1">
        Customization Info
      </h3>
      <textarea 
        value={val}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="Special instructions or custom data for production..."
        rows={2}
        className="w-full bg-zinc-950/50 border border-zinc-800 rounded-lg p-3 text-xs text-zinc-300 placeholder:text-zinc-700 focus:outline-none focus:border-teal-500/30 transition-all resize-none shadow-inner"
      />
    </div>
  );
}

export function DetailInternalNotes({ order, onUpdate }: NoteProps) {
  const [val, setVal] = useState(order.internal_note || '');

  useEffect(() => {
    setVal(order.internal_note || '');
  }, [order.id, order.internal_note]);

  const debouncedSave = useCallback(
    debounce(async (v: string) => {
      await onUpdate({ internal_note: v });
    }, 1000),
    [onUpdate]
  );

  const handleChange = (v: string) => {
    setVal(v);
    debouncedSave(v);
  };

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4">
      <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-3 px-1">
        Internal Notes
      </h3>
      <textarea 
        value={val}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="Add private team-only notes about this order..."
        rows={2}
        className="w-full bg-zinc-950/50 border border-zinc-800 rounded-lg p-3 text-xs text-zinc-300 placeholder:text-zinc-700 focus:outline-none focus:border-teal-500/30 transition-all resize-none shadow-inner"
      />
    </div>
  );
}
