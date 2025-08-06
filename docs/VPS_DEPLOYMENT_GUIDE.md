# VPS Deployment Guide for DispatchAI

This guide provides step-by-step instructions for deploying DispatchAI to a VPS (Virtual Private Server) using Docker Compose. Optimized for providers like Hetzner, Vultr, or Linode.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Server Setup](#server-setup)
3. [Docker Installation](#docker-installation)
4. [Security Configuration](#security-configuration)
5. [Application Deployment](#application-deployment)
6. [Domain Configuration (Optional)](#domain-configuration-optional)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Resources
- **VPS Specifications:** 8GB RAM, 2+ vCPUs (AMD Shared recommended)
- **Operating System:** Ubuntu 22.04 LTS
- **SSH Key:** Generated and added to VPS provider
- **Domain Name:** Optional but recommended

### Required API Keys
- **OpenAI API Key** - Required for AI classification
- **GitHub Webhook Secret** - Optional but recommended for security
- **Anthropic API Key** - Optional for future Claude integration

---

## Server Setup

### Step 1: Initial Connection and Updates

```bash
# Connect to your server
ssh root@YOUR_SERVER_IP

# Update system packages
sudo apt update && sudo apt upgrade -y

# Install essential tools
sudo apt install -y curl wget git htop nano ufw
```

---

## Docker Installation

### Step 2: Install Docker and Docker Compose

```bash
# Install Docker using official script
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installations
docker --version
docker-compose --version
```

**Expected Output:**
```
Docker version 24.x.x
docker-compose version 2.x.x
```

---

## Security Configuration

### Step 3: Create Deploy User and Configure Security

```bash
# Create non-root user
sudo adduser deploy
sudo usermod -aG docker deploy
sudo usermod -aG sudo deploy

# Copy SSH keys to deploy user
sudo mkdir -p /home/deploy/.ssh
sudo cp ~/.ssh/authorized_keys /home/deploy/.ssh/
sudo chown -R deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys

# Switch to deploy user
su - deploy

# Configure firewall
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

### SSH Security Hardening (Optional)

```bash
# Edit SSH configuration
sudo nano /etc/ssh/sshd_config

# Recommended settings:
# PermitRootLogin no
# PasswordAuthentication no
# PubkeyAuthentication yes

# Restart SSH service
sudo systemctl restart sshd
```

---

## Application Deployment

### Step 4: Clone Repository

```bash
# Clone your DispatchAI repository (as deploy user)
git clone https://github.com/your-username/dispatch-ai.git
cd dispatch-ai

# Verify production files exist
ls -la docker-compose.prod.yml scripts/start-prod.sh
```

### Step 5: Configure Environment Variables

```bash
# Copy environment template
cp .env.prod.example .env.prod

# Edit environment file
nano .env.prod
```

**Configure your `.env.prod` file:**

```bash
# ======================
# DATABASE CONFIGURATION
# ======================
POSTGRES_DB=dispatchai
POSTGRES_USER=postgres
# Generate secure password
POSTGRES_PASSWORD=YOUR_GENERATED_PASSWORD_HERE
DATABASE_URL=postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/dispatchai

# ======================
# AI API CONFIGURATION
# ======================
# OpenAI API key (required for classification)
OPENAI_API_KEY=your_openai_api_key_here

# Anthropic API key (optional, for future Claude integration)
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# ======================
# KAFKA CONFIGURATION
# ======================
KAFKA_BOOTSTRAP_SERVERS=redpanda:9092

# ======================
# SECURITY CONFIGURATION
# ======================
# GitHub webhook secret (optional but recommended)
GITHUB_WEBHOOK_SECRET=your_github_webhook_secret_here

# JWT secret for future authentication
JWT_SECRET_KEY=YOUR_GENERATED_JWT_SECRET_HERE

# ======================
# LOGGING & MONITORING
# ======================
LOG_LEVEL=INFO
ENABLE_METRICS=true
```

### Step 6: Generate Secure Passwords

```bash
# Generate secure PostgreSQL password
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)"

# Generate JWT secret
echo "JWT_SECRET_KEY=$(openssl rand -base64 64)"

# Generate GitHub webhook secret (optional)
echo "GITHUB_WEBHOOK_SECRET=$(openssl rand -hex 32)"
```

### Step 7: Deploy Application

```bash
# Make scripts executable
chmod +x scripts/start-prod.sh scripts/stop-prod.sh

# Start the application
./scripts/start-prod.sh

# Check all services are running
docker-compose -f docker-compose.prod.yml ps
```

### Step 8: Verify Deployment

```bash
# Test health endpoints
curl http://localhost:8000/health  # Ingress service
curl http://localhost:8002/health  # Gateway service
curl http://localhost:3000         # Dashboard

# Check logs if needed
docker-compose -f docker-compose.prod.yml logs -f --tail=50
```

**Expected Health Check Responses:**
```json
{
  "status": "healthy",
  "service": "ingress",
  "version": "0.1.0"
}
```

---

## Domain Configuration (Optional)

### Step 9: Install Nginx Reverse Proxy

```bash
# Install Nginx
sudo apt install nginx

# Create site configuration
sudo nano /etc/nginx/sites-available/dispatchai
```

### Step 10: Configure Nginx

**Add this configuration to `/etc/nginx/sites-available/dispatchai`:**

```nginx
# DispatchAI Nginx Configuration
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    # Dashboard (React SPA)
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
    
    # API Gateway
    location /api {
        proxy_pass http://localhost:8002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # WebSocket connections
    location /ws {
        proxy_pass http://localhost:8002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Webhook endpoint
    location /webhook {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Step 11: Enable Site and SSL

```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/dispatchai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Install Certbot for SSL (optional)
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Verify auto-renewal
sudo certbot renew --dry-run
```

### Step 12: DNS Configuration

Configure these DNS records with your domain provider:

```
Type    Name    Value                   TTL
A       @       YOUR_SERVER_IP          3600
A       www     YOUR_SERVER_IP          3600
```

---

## Troubleshooting

### Common Issues and Solutions

#### 1. Service Won't Start

```bash
# Check service logs
docker-compose -f docker-compose.prod.yml logs service_name

# Check container status
docker-compose -f docker-compose.prod.yml ps

# Restart specific service
docker-compose -f docker-compose.prod.yml restart service_name

# Rebuild service if needed
docker-compose -f docker-compose.prod.yml up --build -d service_name
```

#### 2. Database Connection Issues

```bash
# Check database logs
docker-compose -f docker-compose.prod.yml logs postgres

# Test database connection
docker-compose -f docker-compose.prod.yml exec postgres psql -U postgres -d dispatchai -c "SELECT version();"

# Reset database if needed
docker-compose -f docker-compose.prod.yml down
docker volume rm dispatchai_postgres_data
docker-compose -f docker-compose.prod.yml up -d
```

#### 3. Memory/Performance Issues

```bash
# Check system resources
htop
df -h
free -h

# Check Docker resource usage
docker stats

# Clean up Docker resources
docker system prune -a

# Restart services if needed
./scripts/stop-prod.sh
./scripts/start-prod.sh
```

#### 4. Port Already in Use

```bash
# Check what's using ports
sudo lsof -i :3000
sudo lsof -i :8000
sudo lsof -i :8002

# Kill processes if needed
sudo kill -9 PID_NUMBER
```

### Monitoring Commands

```bash
# View all application logs
docker-compose -f docker-compose.prod.yml logs -f --tail=100

# Monitor system resources
htop

# Check disk usage
df -h

# Monitor Docker containers
docker stats

# Check service health
curl http://localhost:8000/health
curl http://localhost:8002/health
curl http://localhost:3000
```

### Log Locations

```bash
# Application logs
docker-compose -f docker-compose.prod.yml logs

# Nginx logs (if using domain)
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# System logs
sudo journalctl -u nginx -f
sudo journalctl -u docker -f
```

---

## Maintenance

### Regular Maintenance Tasks

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Clean up Docker resources
docker system prune -f

# Check disk space
df -h

# Monitor service health
curl http://localhost:8000/health
curl http://localhost:8002/health
```

### Application Updates

```bash
# Update application code
cd ~/dispatch-ai
git pull origin main

# Rebuild and restart services
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d

# Verify deployment
./scripts/start-prod.sh
```

---

## Final Verification

After completing the deployment, your DispatchAI system should be accessible at:

- **Dashboard:** http://your-domain.com (or http://your-server-ip:3000)
- **API Gateway:** http://your-domain.com/api (or http://your-server-ip:8002)
- **Webhook Endpoint:** http://your-domain.com/webhook (or http://your-server-ip:8000)

### Success Indicators

✅ All health endpoints return `{"status": "healthy"}`  
✅ Dashboard loads without errors  
✅ Docker containers are running: `docker-compose ps`  
✅ No error messages in logs: `docker-compose logs`  
✅ System resources are stable: `htop`  

**Congratulations! Your DispatchAI system is now deployed and ready for production use.** 🚀

---

## Support

For issues specific to this deployment:

1. **Check logs first:** `docker-compose -f docker-compose.prod.yml logs`
2. **Verify configuration:** Ensure all environment variables are set correctly
3. **Test components:** Use the health check endpoints
4. **System resources:** Monitor CPU, memory, and disk usage

---

*Last Updated: December 2024*  
*Compatible with: Ubuntu 22.04 LTS, Docker 24.x, Docker Compose 2.x*