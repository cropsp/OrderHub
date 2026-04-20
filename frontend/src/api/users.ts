import client from './client';
import type { User } from '../types/user';

export const usersApi = {
  getMe: async (): Promise<User> => {
    const { data } = await client.get<User>('/users/me');
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
