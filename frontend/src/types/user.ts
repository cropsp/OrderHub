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
  is_active: boolean;
  preferences: Record<string, any>;
  created_at: string;
  updated_at: string;
  // USER-ACCESS-2: effective money-visibility capabilities, populated on
  // /users/me only (role default + explicit overrides; every capability for an
  // owner). Absent on the users-list payload.
  capabilities?: string[];
}

// USER-ACCESS-2 capability names (mirror backend models.user.Capability).
export const Capability = {
  VIEW_FINANCE: 'view_finance',
  VIEW_COSTS: 'view_costs',
} as const;

export type CapabilityType = typeof Capability[keyof typeof Capability];

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
