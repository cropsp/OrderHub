/**
 * OrderHub CRM — Order Cases API client (CASE-1)
 *
 * OWNER + MANAGER only; the router is role-gated server-side, so a DESIGNER
 * gets 403 from every call here. The UI hides the surfaces rather than relying
 * on that, but the gate is what makes it true.
 */

import client from '@/api/client'
import type {
  OpenCasesResponse,
  OrderCase,
  OrderCaseCreatePayload,
  OrderCaseUpdatePayload,
} from '@/types/orderCase'

export const orderCasesApi = {
  /** Every case on one order, resolved included, newest first. */
  listForOrder: async (orderId: string): Promise<OrderCase[]> => {
    const { data } = await client.get<OrderCase[]>(
      `/cases/order/${encodeURIComponent(orderId)}`,
    )
    return data
  },

  create: async (
    orderId: string,
    payload: OrderCaseCreatePayload,
  ): Promise<OrderCase> => {
    const { data } = await client.post<OrderCase>(
      `/cases/order/${encodeURIComponent(orderId)}`,
      payload,
    )
    return data
  },

  update: async (
    caseId: string,
    payload: OrderCaseUpdatePayload,
  ): Promise<OrderCase> => {
    const { data } = await client.patch<OrderCase>(
      `/cases/${encodeURIComponent(caseId)}`,
      payload,
    )
    return data
  },

  /** Append to the timeline. Returns the whole case — one round trip. */
  addNote: async (caseId: string, text: string): Promise<OrderCase> => {
    const { data } = await client.post<OrderCase>(
      `/cases/${encodeURIComponent(caseId)}/notes`,
      { text },
    )
    return data
  },

  /** Open cases for the dashboard block, scoped to the caller's shops. */
  listOpen: async (): Promise<OpenCasesResponse> => {
    const { data } = await client.get<OpenCasesResponse>('/cases/open')
    return data
  },
}
