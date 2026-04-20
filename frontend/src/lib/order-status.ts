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
    id: 'new',
    label: 'New',
    statuses: [ORDER_STATUS.NEW],
    color: 'teal',
  },
  {
    id: 'awaiting',
    label: 'Awaiting',
    statuses: [ORDER_STATUS.WAITING_INFO, ORDER_STATUS.INFO_RECEIVED],
    color: 'sky',
  },
  {
    id: 'design',
    label: 'Design',
    statuses: [ORDER_STATUS.DESIGN_PENDING, ORDER_STATUS.DESIGN_READY],
    color: 'indigo',
  },
  {
    id: 'production',
    label: 'Production',
    statuses: [ORDER_STATUS.IN_PRODUCTION],
    color: 'amber',
  },
  {
    id: 'shipping',
    label: 'Shipping',
    statuses: [ORDER_STATUS.SHIPPED],
    color: 'orange',
  },
];

export const ARCHIVE_CATEGORIES: StatusCategory[] = [
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
    color: 'slate',
  },
];

// Helper to find category by status
export function getCategoryByStatus(status: OrderStatusValue): StatusCategory | undefined {
  return [...STATUS_CATEGORIES, ...ARCHIVE_CATEGORIES].find((cat) => cat.statuses.includes(status));
}
