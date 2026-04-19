/**
 * OrderHub CRM — Constants
 *
 * Status labels, colors, transitions, and tab groupings.
 */

import type { OrderStatus } from '@/types/common'

// ─── Status Display ─────────────────────────────────────────

export const STATUS_CONFIG: Record<
  OrderStatus,
  { label: string; color: string; bgColor: string }
> = {
  new: { label: 'Нове', color: '#3b82f6', bgColor: '#1e3a5f' },
  waiting_info: { label: 'Очікує інфо', color: '#f59e0b', bgColor: '#422006' },
  info_received: { label: 'Інфо отримано', color: '#8b5cf6', bgColor: '#2e1065' },
  design_pending: { label: 'Дизайн', color: '#ec4899', bgColor: '#500724' },
  design_ready: { label: 'Дизайн готовий', color: '#d946ef', bgColor: '#4a044e' },
  in_production: { label: 'Виробництво', color: '#f97316', bgColor: '#431407' },
  shipped: { label: 'Відправлено', color: '#06b6d4', bgColor: '#083344' },
  completed: { label: 'Завершено', color: '#10b981', bgColor: '#052e16' },
  cancelled: { label: 'Скасовано', color: '#ef4444', bgColor: '#450a0a' },
}

// ─── Status Tabs (group 9 statuses into logical tabs) ────────

export interface StatusTab {
  key: string
  label: string
  statuses: OrderStatus[]
}

export const STATUS_TABS: StatusTab[] = [
  { key: 'all', label: 'Всі', statuses: [] },
  { key: 'new', label: 'Нові', statuses: ['new'] },
  { key: 'awaiting', label: 'Очікування', statuses: ['waiting_info', 'info_received'] },
  { key: 'design', label: 'Дизайн', statuses: ['design_pending', 'design_ready'] },
  { key: 'production', label: 'Виробництво', statuses: ['in_production'] },
  { key: 'shipping', label: 'Доставка', statuses: ['shipped'] },
]

// ─── Status Transitions ─────────────────────────────────────

export const ALLOWED_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  new: ['waiting_info', 'info_received', 'design_pending', 'in_production', 'cancelled'],
  waiting_info: ['info_received', 'cancelled'],
  info_received: ['design_pending', 'in_production', 'cancelled'],
  design_pending: ['design_ready', 'info_received', 'cancelled'],
  design_ready: ['in_production', 'design_pending', 'cancelled'],
  in_production: ['shipped', 'design_pending', 'cancelled'],
  shipped: ['completed', 'in_production'],
  completed: [],
  cancelled: ['new'],
}

// ─── Days Indicator Colors ──────────────────────────────────

export function getDaysColor(days: number): string {
  if (days < 3) return '#10b981' // green
  if (days < 7) return '#f59e0b' // amber
  return '#ef4444' // red
}
