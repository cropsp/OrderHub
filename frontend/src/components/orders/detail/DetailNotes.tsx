import { useState, useCallback } from 'react';
import { debounce } from 'lodash-es';
import type { OrderDetail } from '@/types/order';

interface DetailNotesProps {
  order: OrderDetail;
  onUpdate: (data: Partial<OrderDetail>) => void;
}

export function DetailCustomizationInfo({ order, onUpdate }: DetailNotesProps) {
  const [val, setVal] = useState(order.custom_info || '');
  const [syncedCustomInfo, setSyncedCustomInfo] = useState(order.custom_info);
  if (syncedCustomInfo !== order.custom_info) {
    setSyncedCustomInfo(order.custom_info);
    setVal(order.custom_info || '');
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const debouncedUpdate = useCallback(
    debounce((data: Partial<OrderDetail>) => {
      onUpdate(data);
    }, 1000),
    [onUpdate]
  );

  const handleChange = (newVal: string) => {
    setVal(newVal);
    debouncedUpdate({ custom_info: newVal });
  };

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-zinc-100 mb-3 px-1">
        Notes from customer
      </h3>
      <textarea 
        value={val}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="No notes from customer"
        rows={2}
        className="w-full bg-zinc-950/50 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-teal-500/30 transition-all resize-none shadow-inner italic"
      />
    </div>
  );
}

export function DetailInternalNotes({ order, onUpdate }: DetailNotesProps) {
  const [val, setVal] = useState(order.internal_note || '');
  const [syncedInternal, setSyncedInternal] = useState(order.internal_note);
  if (syncedInternal !== order.internal_note) {
    setSyncedInternal(order.internal_note);
    setVal(order.internal_note || '');
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const debouncedUpdate = useCallback(
    debounce((data: Partial<OrderDetail>) => {
      onUpdate(data);
    }, 1000),
    [onUpdate]
  );

  const handleChange = (newVal: string) => {
    setVal(newVal);
    debouncedUpdate({ internal_note: newVal });
  };

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-zinc-100 mb-3 px-1">
        Internal notes
      </h3>
      <textarea 
        value={val}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="Add a private note..."
        rows={2}
        className="w-full bg-zinc-950/50 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-teal-500/30 transition-all resize-none shadow-inner"
      />
    </div>
  );
}
