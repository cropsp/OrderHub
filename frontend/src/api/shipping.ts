import client from './client'

export const shippingApi = {
  createTTN: async (orderId: string, data: { weight?: number; description?: string }) => {
    const response = await client.post(`/shipping/np-ttn/${orderId}`, data)
    return response.data
  },
}
