import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { authAPI } from '../services/api';

interface User {
  id: string;
  email: string;
  name: string;
}

const useAuth = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const checkAuth = async () => {
      const token = sessionStorage.getItem('token');
      const savedUser = sessionStorage.getItem('user');

      if (token && savedUser) {
        try {
          // Перевіряємо токен через API
          const profile = await authAPI.getProfile();
          setUser(profile.user);
          setIsAuthenticated(true);
        } catch (err) {
          // Якщо токен невалідний, очищаємо
          sessionStorage.removeItem('token');
          sessionStorage.removeItem('user');
          setIsAuthenticated(false);
          setUser(null);
        }
      } else {
        setIsAuthenticated(false);
      }
      setLoading(false);
    };

    checkAuth();
  }, []);

  const login = async (email: string, password: string) => {
    try {
      setError(null);
      const response = await authAPI.login(email, password);
      setUser(response.user);
      setIsAuthenticated(true);
      navigate('/');
      return response;
    } catch (err: any) {
      setError(err.message || 'Login failed');
      throw err;
    }
  };

  const register = async (email: string, password: string, name: string) => {
    try {
      setError(null);
      const response = await authAPI.register(email, password, name);
      setUser(response.user);
      setIsAuthenticated(true);
      navigate('/');
      return response;
    } catch (err: any) {
      setError(err.message || 'Registration failed');
      throw err;
    }
  };

  const logout = () => {
    authAPI.logout();
    setIsAuthenticated(false);
    setUser(null);
    navigate('/login');
  };

  return { 
    isAuthenticated, 
    loading, 
    user, 
    error, 
    login, 
    register, 
    logout 
  };
};

export default useAuth;