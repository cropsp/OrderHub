import { useCallback, useEffect, useRef } from 'react';
import { authApi } from '../api/auth';
import type { LoginCredentials } from '../api/auth';
import { usersApi } from '../api/users';
import { useAuthStore } from '../store/authStore';

export function useAuth() {
  const { user, isAuthenticated, isLoading, setAuth, logout, setLoading } = useAuthStore();
  const initRef = useRef(false);

  const initAuth = useCallback(async () => {
    // Prevent double initialization in strict mode
    if (initRef.current) return;
    initRef.current = true;
    
    setLoading(true);
    try {
      // 1. Refresh to get access token implicitly from cookie
      await authApi.refresh();
      
      // 2. Since we have access token, we can get user info
      const me = await usersApi.getMe();
      setAuth(me);
    } catch {
      // Ignore errors - it just means user isn't logged in
      logout();
    } finally {
      setLoading(false);
    }
  }, [setAuth, logout, setLoading]);

  useEffect(() => {
    initAuth();
  }, [initAuth]);

  const handleLogin = async (credentials: LoginCredentials) => {
    setLoading(true);
    try {
      await authApi.login(credentials);
      // Wait for it to set token, now fetch user
      const me = await usersApi.getMe();
      setAuth(me);
    } catch (err) {
      setLoading(false);
      throw err;
    }
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } finally {
      logout();
    }
  };

  return {
    user,
    isAuthenticated,
    isLoading,
    login: handleLogin,
    logout: handleLogout,
  };
}
