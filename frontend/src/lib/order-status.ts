/**
 * OrderHub CRM — Status Grouping logic
 * 
 * Maps canonical backend statuses to logical UI categories.
 */

export const ORDER_STATUS = {
  NEW: 'new',
  WAITING_INFO: 'waiting_info',
  INFO_RECEIVED: 'info_received',
  DESIGN_PENDING: 'design_pending',
  DESIGN_READY: 'design_ready',
  IN_PRODUCTION: 'in_production',
  SHIPPED: 'shipped',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
} as const;

export type OrderStatusValue = typeof ORDER_STATUS[keyof typeof ORDER_STATUS];

export interface StatusCategory {
  id: string;
  label: string;
  statuses: OrderStatusValue[];
  color: string;
}

export const STATUS_CATEGORIES: StatusCategory[] = [
  {
    id: 'all',
    label: 'All',
    statuses: [],
    color: 'zinc',
  },
  {
    id: 'new',
    label: 'New',
    statuses: [ORDER_STATUS.NEW],
    color: 'teal',
  },
  {
    id: 'waiting_info',
    label: 'Waiting Info',
    statuses: [ORDER_STATUS.WAITING_INFO],
    color: 'sky',
  },
  {
    id: 'info_received',
    label: 'Info Received',
    statuses: [ORDER_STATUS.INFO_RECEIVED],
    color: 'blue',
  },
  {
    id: 'design_pending',
    label: 'Design Pending',
    statuses: [ORDER_STATUS.DESIGN_PENDING],
    color: 'indigo',
  },
  {
    id: 'design_ready',
    label: 'Design Ready',
    statuses: [ORDER_STATUS.DESIGN_READY],
    color: 'violet',
  },
  {
    id: 'production',
    label: 'In Production',
    statuses: [ORDER_STATUS.IN_PRODUCTION],
    color: 'amber',
  },
  {
    id: 'shipping',
    label: 'Shipped',
    statuses: [ORDER_STATUS.SHIPPED],
    color: 'orange',
  },
  {
    id: 'completed',
    label: 'Completed',
    statuses: [ORDER_STATUS.COMPLETED],
    color: 'emerald',
  },
  {
    id: 'cancelled',
    label: 'Cancelled',
    statuses: [ORDER_STATUS.CANCELLED],
    color: 'zinc',
  },
];

export const ARCHIVE_CATEGORIES: StatusCategory[] = []; // Unified into main tabs


// Helper to find category by status
export function getCategoryByStatus(status: OrderStatusValue): StatusCategory | undefined {
  return [...STATUS_CATEGORIES, ...ARCHIVE_CATEGORIES].find((cat) => cat.statuses.includes(status));
}

/** Readable label for a raw order-status enum value (e.g. `in_production` → "In Production"). */
export function statusLabel(status: string): string {
  return getCategoryByStatus(status as OrderStatusValue)?.label ?? status.replace(/_/g, ' ');
}
