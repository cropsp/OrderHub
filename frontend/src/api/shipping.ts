import client from './client'

export interface CreateTTNResponse {
  status: string
  ttn: string
  warnings?: string[]
}

// WB-3 — WesternBid thermal label print.
export interface WbLabelCandidate {
  shipment_id: string
  recipient_name: string | null
  recipient_postal_code: string | null
  recipient_country_code: string | null
  created_date: string | null
  shipping_type: string | null
  carrier_type: string | null
}

export interface WbLabelCandidatesResponse {
  status: 'cached' | 'linked' | 'candidates' | 'empty'
  attachment_id?: string | null
  file_name?: string | null
  candidates: WbLabelCandidate[]
}

export interface WbLabelResponse {
  status: 'success' | 'unsupported'
  attachment_id?: string | null
  file_name?: string | null
  message?: string | null
}

export const shippingApi = {
  createTTN: async (orderId: string, data: {
    weight?: number;
    volume?: number;
    length?: number;
    width?: number;
    height?: number;
    description?: string;
    cash_on_delivery?: boolean;
    cod_amount?: number;
    parcel_override?: boolean;
  }) => {
    const response = await client.post<CreateTTNResponse>(`/shipping/np-ttn/${orderId}`, data)
    return response.data
  },
  getParcelEstimate: async (orderId: string) => {
    const response = await client.get(`/orders/${orderId}/parcel-estimate`)
    return response.data
  },
  deleteTTN: async (orderId: string): Promise<{ status: 'success' | 'soft_success'; message: string }> => {
    const response = await client.delete(`/shipping/np-ttn/${orderId}`)
    return response.data
  },
  searchCities: async (query: string) => {
    const response = await client.get(`/shipping/cities`, { params: { query } })
    return response.data
  },
  getWarehouses: async (cityRef: string, query: string = "") => {
    const response = await client.get(`/shipping/warehouses/${cityRef}`, { params: { query } })
    return response.data
  },
  // WB-3: find candidate WB parcels for an order (manager-confirmed match).
  wbLabelCandidates: async (orderId: string, broaden = false): Promise<WbLabelCandidatesResponse> => {
    const response = await client.get<WbLabelCandidatesResponse>(
      `/shipping/wb-label/${orderId}/candidates`,
      { params: { broaden } },
    )
    return response.data
  },
  // WB-3: confirm the parcel, fetch the correct label, cache it as an attachment.
  wbLabelFetch: async (orderId: string, shipmentId: string): Promise<WbLabelResponse> => {
    const response = await client.post<WbLabelResponse>(`/shipping/wb-label/${orderId}`, {
      shipment_id: shipmentId,
    })
    return response.data
  },
}
