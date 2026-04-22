import client from './client'

export const shippingApi = {
  createTTN: async (orderId: string, data: { weight?: number; description?: string }) => {
    const response = await client.post(`/shipping/np-ttn/${orderId}`, data)
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
