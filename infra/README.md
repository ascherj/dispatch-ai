# Infrastructure

Docker Compose and deployment configurations.

## Purpose

This directory contains all infrastructure-related configurations including Docker Compose for local development and Fly.io configurations for production deployment.

## Contents

- `docker-compose.yml` - Local development environment
- `fly.toml` - Fly.io deployment configuration
- Environment variable templates
- Database migration scripts
- Monitoring configurations

## Setup

Coming soon - see main project README for development setup.

## Services

- Redpanda (Kafka-compatible message broker)
- PostgreSQL 16 with pgvector extension
- Development containers for all services
- Monitoring stack (Prometheus, Loki, Grafana)
