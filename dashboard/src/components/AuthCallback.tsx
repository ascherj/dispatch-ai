import React, { useEffect, useState } from 'react';
import { useAuth } from '../hooks/useAuth';

const AuthCallback: React.FC = () => {
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);

  useEffect(() => {
    const handleCallback = async () => {
      // Prevent multiple simultaneous callback processing
      if (isProcessing) {
        return;
      }
      setIsProcessing(true);
      try {
        // Get the authorization code from URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const code = urlParams.get('code');
        const state = urlParams.get('state');
        const error = urlParams.get('error');

        if (error) {
          setError(`GitHub OAuth error: ${error}`);
          setIsLoading(false);
          setIsProcessing(false);
          return;
        }

        if (!code) {
          setError('No authorization code received');
          setIsLoading(false);
          setIsProcessing(false);
          return;
        }

        // Exchange code for access token using refactored auth service
        const authUrl = import.meta.env.VITE_AUTH_URL || 'http://localhost:8003';
        const response = await fetch(`${authUrl}/auth/github/callback`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ code, state }),
        });

        if (!response.ok) {
          const errorData = await response.json();
          setError(errorData.detail || 'Authentication failed');
          setIsLoading(false);
          setIsProcessing(false);
          return;
        }

        const authData = await response.json();

        // Log in the user
        login(authData);

        // Redirect to main dashboard
        window.location.href = '/';

      } catch (err) {
        console.error('Authentication callback error:', err);
        setError('Authentication failed. Please try again.');
        setIsLoading(false);
        setIsProcessing(false);
      }
    };

    handleCallback();
  }, [login]); // Removed isProcessing from dependencies to prevent infinite loop

  if (isLoading) {
    return (
      <div className="auth-callback">
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Completing authentication...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="auth-callback">
        <div className="error-container">
          <h2>Authentication Error</h2>
          <p>{error}</p>
          <button onClick={() => window.location.href = '/'}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return null;
};

export default AuthCallback;
