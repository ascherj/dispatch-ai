import React from 'react';
import LoginButton from './LoginButton';
import './WelcomePage.css';

const WelcomePage: React.FC = () => {
  return (
    <div className="welcome-page">
      <div className="welcome-content">
        <div className="welcome-header">
          <span className="logo-icon">⚡</span>
          <h1>Welcome to DispatchAI</h1>
          <p className="welcome-subtitle">
            Intelligent GitHub issue classification and triaging system
          </p>
        </div>

        <div className="welcome-features">
          <div className="feature-card">
            <div className="feature-icon">🤖</div>
            <h3>AI-Powered Classification</h3>
            <p>
              Automatically categorize and prioritize your GitHub issues using
              advanced AI analysis for faster triaging.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">⚡</div>
            <h3>Real-Time Processing</h3>
            <p>
              Get instant classifications as issues are created or updated,
              with live dashboard updates via WebSocket connections.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🎯</div>
            <h3>Smart Insights</h3>
            <p>
              Track issue patterns, analyze sentiment, and get actionable
              insights to improve your development workflow.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-icon">🔄</div>
            <h3>Human-in-the-Loop</h3>
            <p>
              Review and correct AI classifications to continuously improve
              accuracy and adapt to your project's specific needs.
            </p>
          </div>
        </div>

        <div className="welcome-cta">
          <h2>Get Started</h2>
          <p>
            Sign in with your GitHub account to connect your repositories
            and start experiencing intelligent issue management.
          </p>

          <div className="cta-buttons">
            <LoginButton />
          </div>

          <div className="welcome-benefits">
            <h4>What you can do after signing in:</h4>
            <ul>
              <li>Connect your GitHub repositories</li>
              <li>View AI-classified issues in real-time</li>
              <li>Manually sync existing issues for analysis</li>
              <li>Correct classifications to improve AI accuracy</li>
              <li>Track issue patterns and analytics</li>
            </ul>
          </div>
        </div>
      </div>

    </div>
  );
};

export default WelcomePage;