import { Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useState } from 'react';

import { ProductVariantSelector } from '@/components/orders/ProductVariantSelector';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { OrderItem } from '@/types/common';
import type { OrderDetail } from '@/types/order';

type NewItem = {
  _key: string;
  title: string;
  quantity: number;
  unit_price: number;
  product_variant_id?: string;
};

interface DetailItemsProps {
  order: OrderDetail;
  isEditable: boolean;
  onAddItem: (payload: {
    title: string;
    quantity: number;
    unit_price: number;
    product_variant_id?: string;
  }) => Promise<void>;
  onUpdateItem: (
    itemId: string,
    payload: {
      title?: string;
      quantity?: number;
      unit_price?: number;
      product_variant_id?: string;
    },
  ) => Promise<void>;
  onDeleteItem: (itemId: string) => Promise<void>;
}

function makeKey() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `new-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

function diffPayload(
  edited: OrderItem,
  original: OrderItem,
): { title?: string; quantity?: number; unit_price?: number; product_variant_id?: string } | null {
  const payload: {
    title?: string;
    quantity?: number;
    unit_price?: number;
    product_variant_id?: string;
  } = {};
  if (edited.title !== original.title) payload.title = edited.title;
  if (edited.quantity !== original.quantity) payload.quantity = edited.quantity;
  if (edited.unit_price !== original.unit_price) payload.unit_price = edited.unit_price;
  if (edited.product_variant_id !== original.product_variant_id) {
    payload.product_variant_id = edited.product_variant_id ?? undefined;
  }
  return Object.keys(payload).length > 0 ? payload : null;
}

export function DetailItems({
  order,
  isEditable,
  onAddItem,
  onUpdateItem,
  onDeleteItem,
}: DetailItemsProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedItems, setEditedItems] = useState<OrderItem[]>([]);
  const [newItems, setNewItems] = useState<NewItem[]>([]);
  const [deletedItemIds, setDeletedItemIds] = useState<Set<string>>(new Set());
  const [isSaving, setIsSaving] = useState(false);

  const enterEditMode = () => {
    setEditedItems((order.items ?? []).map((item) => ({ ...item })));
    setNewItems([]);
    setDeletedItemIds(new Set());
    setIsEditing(true);
  };

  const exitEditMode = () => {
    setEditedItems([]);
    setNewItems([]);
    setDeletedItemIds(new Set());
    setIsEditing(false);
  };

  const updateEditedField = <K extends keyof OrderItem>(idx: number, field: K, value: OrderItem[K]) => {
    setEditedItems((prev) => prev.map((item, i) => (i === idx ? { ...item, [field]: value } : item)));
  };

  const updateNewField = <K extends keyof NewItem>(idx: number, field: K, value: NewItem[K]) => {
    setNewItems((prev) => prev.map((item, i) => (i === idx ? { ...item, [field]: value } : item)));
  };

  const removeEditedItem = (idx: number) => {
    setEditedItems((prev) => {
      const removed = prev[idx];
      if (removed) {
        setDeletedItemIds((d) => {
          const next = new Set(d);
          next.add(removed.id);
          return next;
        });
      }
      return prev.filter((_, i) => i !== idx);
    });
  };

  const removeNewItem = (idx: number) => {
    setNewItems((prev) => prev.filter((_, i) => i !== idx));
  };

  const addBlankItem = () => {
    setNewItems((prev) => [
      ...prev,
      { _key: makeKey(), title: '', quantity: 1, unit_price: 0 },
    ]);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      for (const id of deletedItemIds) {
        await onDeleteItem(id);
      }
      const originals = new Map((order.items ?? []).map((it) => [it.id, it]));
      for (const item of editedItems) {
        const original = originals.get(item.id);
        if (!original) continue;
        const payload = diffPayload(item, original);
        if (payload) {
          await onUpdateItem(item.id, payload);
        }
      }
      for (const item of newItems) {
        await onAddItem({
          title: item.title,
          quantity: item.quantity,
          unit_price: item.unit_price,
          product_variant_id: item.product_variant_id,
        });
      }
      exitEditMode();
    } catch {
      // Errors surface via toast in the controller. Stay in edit mode so user can retry/cancel.
    } finally {
      setIsSaving(false);
    }
  };

  const totalRows = editedItems.length + newItems.length;
  const editingSubtotal =
    editedItems.reduce((acc, it) => acc + it.quantity * it.unit_price, 0) +
    newItems.reduce((acc, it) => acc + it.quantity * it.unit_price, 0);
  const editingItemCount =
    editedItems.reduce((acc, it) => acc + it.quantity, 0) +
    newItems.reduce((acc, it) => acc + it.quantity, 0);

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl overflow-hidden shadow-sm">
      <div className="px-4 py-3 border-b border-zinc-800/50 bg-zinc-900/20 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-100">Product inventory</h3>
        {isEditable && !isEditing && (
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            onClick={enterEditMode}
            className="text-zinc-500 hover:text-teal-400 hover:bg-teal-500/10"
            aria-label="Edit items"
          >
            <Pencil className="size-3.5" />
          </Button>
        )}
        {isEditable && isEditing && (
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="xs"
              onClick={exitEditMode}
              disabled={isSaving}
              className="text-zinc-400 hover:text-zinc-200"
            >
              <X className="size-3.5" /> Cancel
            </Button>
            <Button
              type="button"
              variant="default"
              size="xs"
              onClick={handleSave}
              disabled={isSaving || totalRows === 0}
              className="bg-teal-500/20 text-teal-300 hover:bg-teal-500/30 border border-teal-500/30"
            >
              {isSaving ? <Loader2 className="size-3.5 animate-spin" /> : null}
              {isSaving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        )}
      </div>

      {!isEditing ? (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-zinc-800/30 bg-zinc-900/40">
                  <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500">Item details</th>
                  <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 text-right">Qty</th>
                  <th className="px-4 py-2.5 text-[11px] font-medium text-zinc-500 text-right">Unit price</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/20">
                {order.items?.map((item) => (
                  <tr key={item.id} className="group hover:bg-white/[0.01] transition-colors">
                    <td className="px-4 py-4">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-sm font-semibold text-zinc-200 group-hover:text-teal-400 transition-colors leading-tight flex items-center gap-2">
                          {item.title}
                          {!item.product_variant_id && (
                            <span className="text-[10px] font-medium text-amber-500/80 bg-amber-500/5 px-1.5 py-0.5 rounded border border-amber-500/10">
                              Unlinked
                            </span>
                          )}
                        </span>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[11px] font-mono text-zinc-500 uppercase tracking-tight">
                            SKU: {item.sku || 'N/A'}
                          </span>
                          {item.snapshot_title && item.snapshot_title !== item.title && (
                            <>
                              <span className="text-zinc-800">·</span>
                              <span className="text-[11px] text-teal-500/70 font-medium">
                                 Ref: {item.snapshot_title}
                              </span>
                            </>
                          )}
                          {item.variations && (
                            <>
                              <span className="text-zinc-800">·</span>
                              <span className="text-[11px] text-zinc-500 italic">
                                {item.variations}
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-right align-top">
                      <span className="text-sm font-medium text-zinc-400">
                        ×{item.quantity}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-right align-top">
                      <span className="text-sm font-medium text-zinc-300">
                        {item.unit_price.toFixed(2)} <span className="text-[11px] text-zinc-600 uppercase ml-0.5">{order.currency}</span>
                      </span>
                    </td>
                  </tr>
                ))}
                <tr className="bg-zinc-950/30 border-t border-zinc-800/50">
                  <td colSpan={2} className="px-4 py-3.5 text-right">
                    <span className="text-sm font-medium text-zinc-500">Subtotal</span>
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <span className="text-sm font-bold text-zinc-100">
                      {order.total_price.toFixed(2)} <span className="text-[11px] text-zinc-500 uppercase ml-0.5">{order.currency}</span>
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="px-4 py-2 bg-zinc-950/50 border-t border-zinc-800/30 flex justify-end">
            <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
              Total Items: <span className="text-zinc-400 ml-1">{order.items?.reduce((acc, item) => acc + item.quantity, 0)}</span>
            </p>
          </div>
        </>
      ) : (
        <>
          <div className="p-4 space-y-3">
            {editedItems.map((item, idx) => (
              <div
                key={item.id}
                className="flex flex-wrap sm:flex-nowrap items-end gap-3"
              >
                <div className="flex-1 min-w-[200px]">
                  <ProductVariantSelector
                    shopId={order.shop_id}
                    value={item.title}
                    onChange={(title, variantId, price) => {
                      updateEditedField(idx, 'title', title);
                      if (variantId !== undefined) {
                        updateEditedField(idx, 'product_variant_id', variantId ?? null);
                      }
                      if (price !== undefined) {
                        updateEditedField(idx, 'unit_price', price);
                      }
                    }}
                  />
                </div>
                <Input
                  type="number"
                  className="w-16 h-9 border-zinc-800 bg-zinc-900/40 rounded-lg text-center text-zinc-100"
                  value={item.quantity}
                  onChange={(e) =>
                    updateEditedField(idx, 'quantity', parseInt(e.target.value) || 1)
                  }
                />
                <div className="relative w-24">
                  <Input
                    type="number"
                    step="0.01"
                    className="h-9 border-zinc-800 bg-zinc-900/40 rounded-lg text-right pr-10 text-zinc-100"
                    value={item.unit_price}
                    onChange={(e) =>
                      updateEditedField(idx, 'unit_price', parseFloat(e.target.value) || 0)
                    }
                  />
                  <span className="absolute right-2.5 top-2.5 text-[10px] font-bold text-zinc-600 uppercase">
                    {order.currency}
                  </span>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-9 text-zinc-600 hover:text-red-400 rounded-lg"
                  onClick={() => removeEditedItem(idx)}
                  disabled={totalRows === 1 || isSaving}
                  aria-label="Remove item"
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            ))}

            {newItems.map((item, idx) => (
              <div
                key={item._key}
                className="flex flex-wrap sm:flex-nowrap items-end gap-3"
              >
                <div className="flex-1 min-w-[200px]">
                  <ProductVariantSelector
                    shopId={order.shop_id}
                    value={item.title}
                    onChange={(title, variantId, price) => {
                      updateNewField(idx, 'title', title);
                      if (variantId !== undefined) {
                        updateNewField(idx, 'product_variant_id', variantId ?? undefined);
                      }
                      if (price !== undefined) {
                        updateNewField(idx, 'unit_price', price);
                      }
                    }}
                  />
                </div>
                <Input
                  type="number"
                  className="w-16 h-9 border-zinc-800 bg-zinc-900/40 rounded-lg text-center text-zinc-100"
                  value={item.quantity}
                  onChange={(e) =>
                    updateNewField(idx, 'quantity', parseInt(e.target.value) || 1)
                  }
                />
                <div className="relative w-24">
                  <Input
                    type="number"
                    step="0.01"
                    className="h-9 border-zinc-800 bg-zinc-900/40 rounded-lg text-right pr-10 text-zinc-100"
                    value={item.unit_price}
                    onChange={(e) =>
                      updateNewField(idx, 'unit_price', parseFloat(e.target.value) || 0)
                    }
                  />
                  <span className="absolute right-2.5 top-2.5 text-[10px] font-bold text-zinc-600 uppercase">
                    {order.currency}
                  </span>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-9 text-zinc-600 hover:text-red-400 rounded-lg"
                  onClick={() => removeNewItem(idx)}
                  disabled={totalRows === 1 || isSaving}
                  aria-label="Remove item"
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            ))}

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={addBlankItem}
              disabled={isSaving}
              className="h-8 text-teal-400 hover:text-teal-300 hover:bg-teal-500/10 rounded-lg text-xs"
            >
              <Plus className="mr-1.5 size-3.5" /> Add item
            </Button>
          </div>

          <div className="px-4 py-3 bg-zinc-950/30 border-t border-zinc-800/50 flex justify-between items-center">
            <span className="text-sm font-medium text-zinc-500">Subtotal</span>
            <span className="text-sm font-bold text-zinc-100">
              {editingSubtotal.toFixed(2)}{' '}
              <span className="text-[11px] text-zinc-500 uppercase ml-0.5">{order.currency}</span>
            </span>
          </div>
          <div className="px-4 py-2 bg-zinc-950/50 border-t border-zinc-800/30 flex justify-end">
            <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
              Total Items: <span className="text-zinc-400 ml-1">{editingItemCount}</span>
            </p>
          </div>
        </>
      )}
    </div>
  );
}
