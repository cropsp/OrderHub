import client from './client'

export interface CreateTTNResponse {
  status: string
  ttn: string
  warnings?: string[]
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
  deleteTTN: async (orderId: string) => {
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
}
