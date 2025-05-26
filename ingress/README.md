# Ingress Service

FastAPI webhook receiver for GitHub events.

## Purpose

This service receives and validates GitHub webhook events for issues, issue comments, and pull requests, then forwards them to the Kafka message queue for processing.

## Features

- Secure webhook validation with GitHub signatures
- FastAPI-based REST endpoints
- Kafka producer integration
- Request logging and monitoring

## Setup

Coming soon - see main project README for development setup.

## API Endpoints

- `POST /webhook` - GitHub webhook receiver
- `GET /health` - Health check endpoint
