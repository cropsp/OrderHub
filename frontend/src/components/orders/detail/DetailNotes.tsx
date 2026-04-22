import { useState, useEffect, useCallback } from 'react';
import { debounce } from 'lodash-es';
import { ClipboardList, Info } from 'lucide-react';
import { BentoCard } from './BentoCard';
import type { OrderDetail } from '@/types/order';

interface DetailNotesProps {
  order: OrderDetail;
  onUpdate: (payload: any) => Promise<void>;
}

export function DetailNotes({ order, onUpdate }: DetailNotesProps) {
  const [internalNote, setInternalNote] = useState(order.internal_note || '');
  const [customInfo, setCustomInfo] = useState(order.custom_info || '');

  useEffect(() => {
    setInternalNote(order.internal_note || '');
    setCustomInfo(order.custom_info || '');
  }, [order.id, order.internal_note, order.custom_info]);

  const debouncedSave = useCallback(
    debounce(async (payload: any) => {
      await onUpdate(payload);
    }, 1000),
    [onUpdate]
  );

  const handleNoteChange = (val: string) => {
    setInternalNote(val);
    debouncedSave({ internal_note: val });
  };

  const handleCustomInfoChange = (val: string) => {
    setCustomInfo(val);
    debouncedSave({ custom_info: val });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
      <BentoCard title="Internal Notes" icon={ClipboardList}>
        <textarea 
          value={internalNote}
          onChange={(e) => handleNoteChange(e.target.value)}
          placeholder="Add private team-only notes about this order..."
          className="w-full bg-transparent border-none p-0 focus:outline-none resize-none min-h-[140px] text-zinc-300 text-sm leading-relaxed placeholder:text-zinc-700"
        />
      </BentoCard>

      <BentoCard title="Customization Info" icon={Info}>
        <textarea 
          value={customInfo}
          onChange={(e) => handleCustomInfoChange(e.target.value)}
          placeholder="Special instructions or custom data for production..."
          className="w-full bg-transparent border-none p-0 focus:outline-none resize-none min-h-[140px] text-teal-400 font-medium text-sm leading-relaxed placeholder:text-zinc-700"
        />
      </BentoCard>
    </div>
  );
}
