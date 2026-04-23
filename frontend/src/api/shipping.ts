import client from './client'

export const shippingApi = {
  createTTN: async (orderId: string, data: { 
    weight?: number; 
    volume?: number; 
    description?: string;
    cash_on_delivery?: boolean;
    cod_amount?: number;
  }) => {
    const response = await client.post(`/shipping/np-ttn/${orderId}`, data)
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
