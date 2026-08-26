/**
 * OrderHub CRM — Order Case types (CASE-1)
 *
 * Mirrors `backend/schemas/order_case.py`. The backend stores `case_type`,
 * `status` and `kind` as plain strings (the `Capability` precedent) and
 * validates them with Python enums at the API boundary, so the vocabulary can
 * grow without a migration. These unions are the same contract on this side —
 * and every consumer below falls back rather than crashing on a value it does
 * not recognise, because the server may grow one before the frontend ships.
 */

export const CASE_TYPES = [
  'return',
  'lost_parcel',
  'reship',
  'review',
  'address_issue',
  'claim',
  'other',
] as const

export type CaseType = (typeof CASE_TYPES)[number]

export const CASE_STATUSES = ['in_progress', 'waiting', 'resolved'] as const

export type CaseStatus = (typeof CASE_STATUSES)[number]

/** 'system' rows are written by the server on a status change. */
export type CaseNoteKind = 'comment' | 'system'

export interface OrderCaseNote {
  id: string
  kind: CaseNoteKind
  text: string
  created_at: string
  author_id: string
  author_name: string | null
}

export interface OrderCase {
  id: string
  order_id: string
  case_type: string
  title: string
  status: string
  next_action: string | null
  due_at: string | null
  owner_id: string | null
  owner_name: string | null
  created_by_id: string
  created_by_name: string | null
  resolved_at: string | null
  resolution_note: string | null
  created_at: string
  updated_at: string
  notes: OrderCaseNote[]
}

/**
 * A dashboard row. Deliberately without `notes` — the block renders none, and
 * the server does not send them.
 */
export interface OpenCaseRow {
  id: string
  order_id: string
  case_type: string
  title: string
  status: string
  next_action: string | null
  due_at: string | null
  owner_id: string | null
  owner_name: string | null
  created_at: string
  order_number: string | null
  order_external_id: string | null
  customer_name: string | null
  shop_id: string
  shop_name: string | null
}

export interface OpenCasesResponse {
  in_progress: OpenCaseRow[]
  waiting: OpenCaseRow[]
}

export interface OrderCaseCreatePayload {
  case_type: CaseType
  title: string
  next_action?: string | null
  due_at?: string | null
  owner_id?: string | null
}

export interface OrderCaseUpdatePayload {
  case_type?: CaseType
  title?: string
  status?: CaseStatus
  next_action?: string | null
  due_at?: string | null
  owner_id?: string | null
  resolution_note?: string | null
}

/** Ukrainian labels. Unknown values fall back to the raw string. */
export const CASE_TYPE_LABELS: Record<string, string> = {
  return: 'Повернення',
  lost_parcel: 'Загублена посилка',
  reship: 'Переслати',
  review: 'Відгук',
  address_issue: 'Проблема з адресою',
  claim: 'Претензія',
  other: 'Інше',
}

export const CASE_STATUS_LABELS: Record<string, string> = {
  in_progress: 'В роботі',
  waiting: 'Чекаємо',
  resolved: 'Вирішено',
}

export function caseTypeLabel(value: string): string {
  return CASE_TYPE_LABELS[value] ?? value
}

export function caseStatusLabel(value: string): string {
  return CASE_STATUS_LABELS[value] ?? value
}

/**
 * Is this case past its deadline?
 *
 * Computed here rather than sent by the server on purpose: a `days_overdue`
 * float on the wire would pull a feature that handles no money onto the
 * money-classification surface that `test_money_field_completeness.py` guards,
 * for a subtraction the browser can do. A case with no `due_at` is never
 * overdue — an undated case is not late.
 */
export function isOverdue(dueAt: string | null, now: Date = new Date()): boolean {
  if (!dueAt) return false
  return new Date(dueAt).getTime() < now.getTime()
}
