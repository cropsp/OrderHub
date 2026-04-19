export const UserRole = {
  OWNER: 'owner',
  MANAGER: 'manager',
  DESIGNER: 'designer',
} as const;

export type UserRoleType = typeof UserRole[keyof typeof UserRole];

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRoleType;
  is_active: string;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setAuth: (user: User) => void;
  logout: () => void;
  setLoading: (isLoading: boolean) => void;
}
