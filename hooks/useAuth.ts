
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const useAuth = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const navigate = useNavigate();

  useEffect(() => {
    const token = sessionStorage.getItem('mock_jwt');
    setIsAuthenticated(!!token);
    setLoading(false);
  }, []);

  const login = () => {
    sessionStorage.setItem('mock_jwt', 'this-is-a-mock-jwt-token');
    setIsAuthenticated(true);
    navigate('/');
  };

  const logout = () => {
    sessionStorage.removeItem('mock_jwt');
    setIsAuthenticated(false);
    navigate('/login');
  };

  return { isAuthenticated, loading, login, logout };
};

export default useAuth;
