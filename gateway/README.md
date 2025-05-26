# Gateway Service

WebSocket/REST API for real-time updates and client communication.

## Purpose

This service consumes enriched issues from Kafka and provides real-time updates to clients via WebSockets and REST APIs.

## Features

- WebSocket connections for real-time updates
- REST API for querying enriched issues
- Kafka consumer for enriched issues
- Client connection management
- Real-time filtering and sorting

## Setup

Coming soon - see main project README for development setup.

## API Endpoints

- `GET /api/issues` - List enriched issues with filtering
- `GET /api/issues/{id}` - Get specific issue details
- `WS /ws` - WebSocket connection for real-time updates
