import { createContext } from 'react';

export interface User {
  id: number;
  github_id: number;
  username: string;
  email?: string;
  created_at: string;
  properties?: Record<string, unknown>;
}

export interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (authData: { access_token: string; user: User }) => void;
  logout: () => void;
  isAuthenticated: boolean;
  isLoading: boolean;
  refreshUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);