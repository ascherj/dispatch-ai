import React, { useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { AuthContext, type User, type AuthContextType } from './AuthContextTypes';

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load auth state from localStorage on mount
  useEffect(() => {
    const savedToken = localStorage.getItem('auth_token');
    const savedUser = localStorage.getItem('auth_user');

    if (savedToken && savedUser) {
      try {
        setToken(savedToken);
        setUser(JSON.parse(savedUser));
      } catch (error) {
        console.error('Error parsing saved user data:', error);
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
      }
    }

    setIsLoading(false);
  }, []);

  const login = (authData: { access_token: string; user: User }) => {
    setToken(authData.access_token);
    setUser(authData.user);

    // Save to localStorage
    localStorage.setItem('auth_token', authData.access_token);
    localStorage.setItem('auth_user', JSON.stringify(authData.user));
  };

  const logout = () => {
    setToken(null);
    setUser(null);

    // Clear localStorage
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
  };

  const refreshUser = async () => {
    if (!token) return;

    try {
      const authUrl = import.meta.env.VITE_AUTH_URL || 'http://localhost:8003';
      const response = await fetch(`${authUrl}/auth/user/profile`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
        localStorage.setItem('auth_user', JSON.stringify(userData));
      } else {
        // Token might be invalid, log out
        logout();
      }
    } catch (error) {
      console.error('Error refreshing user:', error);
      // Don't log out on network errors, just log the error
    }
  };

  const isAuthenticated = !!user && !!token;

  const value: AuthContextType = {
    user,
    token,
    login,
    logout,
    isAuthenticated,
    isLoading,
    refreshUser
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
