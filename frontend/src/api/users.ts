import client from './client';
import type { User } from '../types/user';

export interface ShopAccess {
  shop_ids: string[];
}

export interface Capabilities {
  // capability name → effective boolean
  capabilities: Record<string, boolean>;
}

export const usersApi = {
  getMe: async (): Promise<User> => {
    const { data } = await client.get<User>('/users/me');
    return data;
  },

  getShopAccess: async (id: string): Promise<ShopAccess> => {
    const { data } = await client.get<ShopAccess>(`/users/${id}/shop-access`);
    return data;
  },

  setShopAccess: async (
    id: string,
    payload: { shop_ids: string[]; unassign_orders?: boolean },
  ): Promise<ShopAccess> => {
    const { data } = await client.put<ShopAccess>(`/users/${id}/shop-access`, payload);
    return data;
  },

  getCapabilities: async (id: string): Promise<Capabilities> => {
    const { data } = await client.get<Capabilities>(`/users/${id}/capabilities`);
    return data;
  },

  setCapabilities: async (
    id: string,
    capabilities: Record<string, boolean>,
  ): Promise<Capabilities> => {
    const { data } = await client.put<Capabilities>(`/users/${id}/capabilities`, {
      capabilities,
    });
    return data;
  },
  
  list: async (): Promise<User[]> => {
    const { data } = await client.get<User[]>('/users');
    return data;
  },
  
  create: async (payload: any): Promise<any> => {
    const { data } = await client.post('/users', payload);
    return data;
  },
  
  update: async (id: string, payload: any): Promise<User> => {
    const { data } = await client.patch<User>(`/users/${id}`, payload);
    return data;
  },
  
  updatePreferences: async (preferences: any): Promise<User> => {
    const { data } = await client.patch<User>('/users/me/preferences', { preferences });
    return data;
  }
};
