import { useState, useEffect } from 'react';
import type { OrderDetail } from '@/types/order';

interface DetailNotesProps {
  order: OrderDetail;
  onUpdate: (data: Partial<OrderDetail>) => void;
}

export function DetailCustomizationInfo({ order, onUpdate }: DetailNotesProps) {
  const [val, setVal] = useState(order.custom_info || '');

  useEffect(() => {
    setVal(order.custom_info || '');
  }, [order.custom_info]);

  const handleChange = (newVal: string) => {
    setVal(newVal);
    onUpdate({ custom_info: newVal });
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

  useEffect(() => {
    setVal(order.internal_note || '');
  }, [order.internal_note]);

  const handleChange = (newVal: string) => {
    setVal(newVal);
    onUpdate({ internal_note: newVal });
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
