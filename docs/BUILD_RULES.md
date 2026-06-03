# Build Rules

## Monorepo
- `apps/api` contains FastAPI, SQLAlchemy, Alembic, and workflow services.
- `apps/web` contains the Next.js operator UI.
- `data` stores local SQLite databases and generated local artefacts.

## Backend Rules
- Route handlers stay thin.
- Services own status transitions and log creation.
- External providers must be introduced through isolated service modules.
- Secret values are never returned from the API.

## Frontend Rules
- Use TypeScript everywhere.
- Treat the API as the source of truth.
- Keep the UI practical and operator-focused.
- Show loading, empty, and error states for all primary views.

## Local Run Rules
- The app must run without Docker.
- Docker Compose can be added later as an optional convenience layer.
- SQLite path defaults into `data/app.db`.

