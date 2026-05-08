# kond-test-py-svc

A FastAPI service with SQLite for managing users and tasks. Used as a benchmark test target for the KOND quality evaluation framework.

## Usage

```bash
pip install -e ".[dev]"
uvicorn app:app --reload
```

API available at `http://localhost:8000`. Docs at `/docs`.

## Endpoints

- `GET /users/` — list all users
- `GET /users/{id}` — get user by ID
- `POST /users/` — create user (`{"name": "...", "email": "..."}`)
- `GET /tasks/` — list all tasks
- `GET /tasks/{id}` — get task by ID
- `POST /tasks/` — create task (`{"title": "...", "owner_id": N}`)
- `PATCH /tasks/{id}` — update task (`{"done": true}`)

## Conventions

- Pydantic models for all request/response schemas — never pass raw dicts to/from route handlers.
- Dependency injection via `Depends(get_db)` for database sessions — never create sessions manually in route handlers.
- All Python identifiers use `snake_case` — no camelCase, no SCREAMING_CASE except for true constants.
- Type hints required on all function signatures — both parameters and return types.
- Docstrings on all public functions and classes — first line is a one-sentence summary.
- SQLAlchemy models in `app/models.py`, schemas in `app/schemas.py`, routes in `app/routes/`.
- Tests in `tests/` using pytest with `httpx`-backed `TestClient`.
- Database migrations via Alembic in `alembic/` — never modify tables by hand.
- Error responses use `HTTPException` with appropriate status codes (400, 404, 409, 422).
- No global mutable state — all state flows through the database session.
- Configuration via environment variables (not implemented yet — DATABASE_URL is hardcoded as intentional technical debt).

## Testing

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
