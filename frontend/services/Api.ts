// API Service для підключення до бекенду

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';

// Допоміжна функція для отримання токена
const getToken = (): string | null => {
  return sessionStorage.getItem('token');
};

// Базова функція для запитів
const fetchAPI = async (endpoint: string, options: RequestInit = {}) => {
  const token = getToken();
  
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || 'Request failed');
  }

  return response.json();
};

// ========== AUTH ==========

export const authAPI = {
  login: async (email: string, password: string) => {
    const data = await fetchAPI('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    
    // Зберігаємо токен
    if (data.token) {
      sessionStorage.setItem('token', data.token);
      sessionStorage.setItem('user', JSON.stringify(data.user));
    }
    
    return data;
  },

  register: async (email: string, password: string, name: string) => {
    const data = await fetchAPI('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });
    
    if (data.token) {
      sessionStorage.setItem('token', data.token);
      sessionStorage.setItem('user', JSON.stringify(data.user));
    }
    
    return data;
  },

  getProfile: async () => {
    return fetchAPI('/auth/profile');
  },

  logout: () => {
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('user');
  }
};

// ========== PRODUCTS ==========

export const productsAPI = {
  getAll: async () => {
    const data = await fetchAPI('/products');
    return data.products;
  },

  getById: async (id: string) => {
    const data = await fetchAPI(`/products/${id}`);
    return data.product;
  },

  create: async (product: { sku: string; name: string; cost: number; price: number }) => {
    const data = await fetchAPI('/products', {
      method: 'POST',
      body: JSON.stringify(product),
    });
    return data.product;
  },

  update: async (id: string, product: Partial<{ sku: string; name: string; cost: number; price: number }>) => {
    const data = await fetchAPI(`/products/${id}`, {
      method: 'PUT',
      body: JSON.stringify(product),
    });
    return data.product;
  },

  delete: async (id: string) => {
    return fetchAPI(`/products/${id}`, {
      method: 'DELETE',
    });
  }
};

// ========== ORDERS ==========

export const ordersAPI = {
  getAll: async (filters?: {
    source?: string;
    status?: string;
    startDate?: string;
    endDate?: string;
    search?: string;
  }) => {
    const params = new URLSearchParams();
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value);
      });
    }
    
    const queryString = params.toString();
    const endpoint = queryString ? `/orders?${queryString}` : '/orders';
    
    const data = await fetchAPI(endpoint);
    return data.orders;
  },

  getById: async (id: string) => {
    const data = await fetchAPI(`/orders/${id}`);
    return data.order;
  },

  create: async (order: {
    source: string;
    customerName: string;
    customerEmail: string;
    customerAddress: string;
    items: Array<{
      productId: string;
      title: string;
      quantity: number;
      price: number;
      cost?: number;
    }>;
    fees?: number;
  }) => {
    const data = await fetchAPI('/orders', {
      method: 'POST',
      body: JSON.stringify(order),
    });
    return data.order;
  },

  updateStatus: async (id: string, status: string) => {
    const data = await fetchAPI(`/orders/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
    return data.order;
  },

  updateItemCost: async (orderId: string, itemId: string, cost: number) => {
    const data = await fetchAPI(`/orders/${orderId}/item-cost`, {
      method: 'PATCH',
      body: JSON.stringify({ itemId, cost }),
    });
    return data.order;
  },

  delete: async (id: string) => {
    return fetchAPI(`/orders/${id}`, {
      method: 'DELETE',
    });
  }
};

// ========== INTEGRATIONS ==========

export const integrationsAPI = {
  getAll: async () => {
    const data = await fetchAPI('/integrations');
    return data.integrations;
  },

  getByPlatform: async (platform: string) => {
    const data = await fetchAPI(`/integrations/${platform}`);
    return data.integration;
  },

  upsert: async (integration: {
    platform: string;
    apiKey: string;
    apiSecret: string;
    isActive?: boolean;
  }) => {
    const data = await fetchAPI('/integrations', {
      method: 'POST',
      body: JSON.stringify(integration),
    });
    return data.integration;
  },

  sync: async (platform: string) => {
    return fetchAPI(`/integrations/${platform}/sync`, {
      method: 'POST',
    });
  },

  delete: async (platform: string) => {
    return fetchAPI(`/integrations/${platform}`, {
      method: 'DELETE',
    });
  }
};

// ========== HEALTH CHECK ==========

export const healthCheck = async () => {
  const response = await fetch(`${API_URL.replace('/api', '')}/health`);
  return response.json();
};