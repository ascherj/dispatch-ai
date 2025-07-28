#!/bin/bash
set -e

echo "🛑 Stopping DispatchAI Production Environment"

# Stop all services
docker compose -f docker-compose.prod.yml down

echo "🧹 Cleaning up..."

# Optional: Remove volumes (uncomment if you want to reset data)
# echo "⚠️  Removing all data volumes..."
# docker compose -f docker-compose.prod.yml down -v

echo "✅ Production environment stopped"
echo ""
echo "💡 To completely reset (including data):"
echo "   docker compose -f docker-compose.prod.yml down -v"
echo "   docker system prune -f"