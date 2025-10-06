# AGENTS.md - Development Guide for DispatchAI

## Build/Lint/Test Commands
- **Start dev environment**: `make dev` (all services via Docker Compose)
- **Run all tests**: `make test` (requires containers) or `make test-ci` (local)  
- **Single test**: `make test-ingress`, `make test-classifier`, `make test-gateway`, `make test-dashboard`
- **Linting**: `make lint` (all) or `make lint-python`/`make lint-js` (specific)
- **Fix linting**: `make lint-fix`

## Python Code Style (FastAPI Services)
- Use **ruff** for formatting/linting (configured in requirements.txt)
- **Imports**: Standard library first, third-party, then local (separated by blank lines)  
- **Type hints**: Required for all function parameters and returns (`from typing import Dict, Any, Optional`)
- **Docstrings**: Use triple quotes for module docstrings at top of files
- **Models**: Pydantic BaseModel for request/response validation
- **Logging**: Use structlog with JSON processors for structured logging
- **Error handling**: Raise HTTPException with appropriate status codes

## TypeScript/React Code Style (Dashboard)
- **Strict TypeScript**: noUnusedLocals, noUnusedParameters enabled (tsconfig.app.json)
- **Interfaces**: PascalCase naming (`interface Issue {}`, `interface Stats {}`)
- **Components**: Functional components with React 19, hooks pattern
- **Imports**: External packages first, then relative imports
- **State**: Use useState/useEffect hooks, no class components
- **Linting**: ESLint with typescript-eslint, react-hooks rules
- **File extensions**: .tsx for React components, .ts for utilities