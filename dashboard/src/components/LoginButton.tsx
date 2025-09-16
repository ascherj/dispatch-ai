import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';

const LoginButton: React.FC = () => {
  const { isAuthenticated, user, logout } = useAuth();
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async () => {
    setIsLoading(true);

    try {
      // Get GitHub OAuth URL from refactored auth service
      const authUrl = import.meta.env.VITE_AUTH_URL || 'http://localhost:8003';
      const response = await fetch(`${authUrl}/auth/github/authorize`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      console.log( 'dataasdf', data);

      if (data.auth_url) {
        // Redirect to GitHub OAuth
        window.location.href = data.auth_url;
      } else {
        console.error('No auth URL received');
        throw new Error('No authorization URL received from server');
      }
    } catch (error) {
      console.error('Login failed:', error);
      // Show user-friendly error message
      alert('Login failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
  };

  if (isAuthenticated && user) {
    return (
      <div className="auth-section">
        <div className="user-info">
          <span className="username">@{user.username}</span>
          <button
            onClick={handleLogout}
            className="logout-btn"
          >
            Logout
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-section">
      <button
        onClick={handleLogin}
        disabled={isLoading}
        className="login-btn"
      >
        {isLoading ? 'Connecting...' : 'Login with GitHub'}
      </button>
    </div>
  );
};

export default LoginButton;
