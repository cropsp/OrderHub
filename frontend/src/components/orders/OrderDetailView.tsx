import {
  ChevronDown,
  Loader2,
  Check,
  Plus
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { useOrderDetailController } from '@/hooks/useOrderDetailController';
import { ORDER_STATUS } from '@/lib/order-status';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { cn } from '@/lib/utils';

import AttachmentManager from './AttachmentManager';
import { DetailHeader } from './detail/DetailHeader';
import { DetailCustomizationInfo, DetailInternalNotes } from './detail/DetailNotes';
import { DetailItems } from './detail/DetailItems';
import { DetailCustomer } from './detail/DetailCustomer';
import { DetailLogistics } from './detail/DetailLogistics';
import { DetailFinance } from './detail/DetailFinance';
import { DetailTimeline } from './detail/DetailTimeline';

interface OrderDetailViewProps {
  orderId: string;
}

export default function OrderDetailView({ orderId }: OrderDetailViewProps) {
  const navigate = useNavigate();
  const {
    order,
    isLoading,
    isOwner,
    canManageShipping,
    saveStatus,
    handleUpdate,
    handleStatusChange,
    handleGenerateTTN,
    handleDeleteTTN,
    isTTNPending,
  } = useOrderDetailController(orderId);

  if (isLoading || !order) {
    return (
      <div className="max-w-6xl mx-auto p-8 space-y-6 h-full bg-zinc-950">
        <Skeleton className="h-16 w-1/2 bg-zinc-900 rounded-2xl" />
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6 h-full">
          <Skeleton className="h-[500px] bg-zinc-900 rounded-2xl" />
          <Skeleton className="h-[500px] bg-zinc-900 rounded-2xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-full bg-zinc-950 pb-12">
      {/* 1. CLEAN HEADER */}
      <DetailHeader
        order={order}
        saveStatus={saveStatus}
        onStatusChange={handleStatusChange}
        onClose={() => navigate(-1)}
      />

      {/* 2. MAIN CONTENT GRID */}
      <div className="flex-1">
        <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6 p-6 pt-2 items-start">

          {/* LEFT COLUMN: Production Workflow */}
          <div className="space-y-3 min-w-0">
            {/* PRODUCT INVENTORY */}
            <DetailItems order={order} />

            {/* CUSTOMIZATION INFO */}
            <DetailCustomizationInfo
              order={order}
              onUpdate={handleUpdate}
            />

            {/* PRODUCTION ASSETS */}
            <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-sm">
              <div className="flex items-center justify-between mb-4 px-1">
                <h3 className="text-sm font-semibold text-zinc-100">
                  Production assets
                </h3>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-white rounded text-xs font-medium gap-1.5 px-3 transition-all"
                  onClick={() => document.getElementById('file-upload-input')?.click()}
                >
                  <Plus size={14} />
                  Upload file
                </Button>
              </div>
              <AttachmentManager orderId={order.id} />
            </div>

            {/* INTERNAL NOTES */}
            <DetailInternalNotes
              order={order}
              onUpdate={handleUpdate}
            />

            {/* TIMELINE */}
            <DetailTimeline order={order} />
          </div>

          {/* RIGHT COLUMN: Management Sidebar (Sticky) */}
          <aside className="sticky top-20 flex flex-col gap-4">

            {/* 1. ORDER STATUS & ACTIONS */}
            <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-sm">
              <h3 className="text-sm font-semibold text-zinc-100 mb-4 px-1">
                Order status
              </h3>

              <div className="space-y-4">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <div className="flex items-center justify-between bg-zinc-950/40 p-3 rounded-lg border border-zinc-800/50 cursor-pointer hover:bg-zinc-900/60 transition-all group">
                      <div className="flex flex-col gap-1">
                        <span className="text-[11px] text-zinc-500 font-medium leading-none">Current status</span>
                        <div className="mt-1">
                          <StatusBadge status={order.status} size="sm" />
                        </div>
                      </div>
                      <ChevronDown size={14} className="text-zinc-500 group-hover:text-zinc-300 transition-colors" />
                    </div>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" sideOffset={4} className="bg-zinc-900 border-zinc-800 text-zinc-300 w-[240px] p-1.5 rounded-xl shadow-2xl">
                    {Object.entries(ORDER_STATUS).map(([key, value]) => (
                      <DropdownMenuItem
                        key={value}
                        onSelect={() => handleStatusChange(value)}
                        className={cn(
                          "text-[9px] font-bold uppercase tracking-widest p-2 rounded-lg focus:bg-zinc-800 focus:text-white cursor-pointer mb-0.5 last:mb-0",
                          order.status === value ? "bg-teal-500/10 text-teal-400" : ""
                        )}
                      >
                        {key.replace(/_/g, ' ')}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>

                <div className="flex items-center justify-between px-1">
                  <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest flex items-center gap-2">
                     {saveStatus === 'saving' ? (
                       <Loader2 size={10} className="animate-spin text-amber-500" />
                     ) : saveStatus === 'saved' ? (
                       <Check size={10} className="text-emerald-500" />
                     ) : null}
                     {saveStatus === 'saving' ? 'Syncing...' : saveStatus === 'saved' ? 'Saved' : 'Auto-save active'}
                  </span>
                </div>
              </div>
            </div>

            <DetailCustomer order={order} />
            <DetailLogistics
              order={order}
              canManageShipping={canManageShipping}
              isPending={isTTNPending}
              onGenerateTTN={handleGenerateTTN}
              onRemoveTTN={handleDeleteTTN}
              onUpdate={handleUpdate}
            />
            {isOwner && <DetailFinance order={order} />}
          </aside>
        </div>
      </div>
    </div>
  );
}
