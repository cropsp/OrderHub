import client from './client';
import type { User } from '../types/user';

export const usersApi = {
  getMe: async (): Promise<User> => {
    const { data } = await client.get<User>('/users/me');
    return data;
  },
};
