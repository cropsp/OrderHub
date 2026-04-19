import { create } from 'zustand';
import type { AuthState, User } from '../types/user';

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true, // starts loading until we check refresh token
  
  setAuth: (user: User) => set({ user, isAuthenticated: true, isLoading: false }),
  logout: () => set({ user: null, isAuthenticated: false, isLoading: false }),
  setLoading: (isLoading: boolean) => set({ isLoading }),
}));
