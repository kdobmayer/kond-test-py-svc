# Payment Processing Service

A FastAPI-based payment processing service with merchant management, webhook delivery, and reporting.

## Features

- **Payments**: Create, capture, void, and refund payments with idempotency key support
- **Merchants**: CRUD operations with API key management
- **Webhooks**: Register endpoints, deliver events with HMAC-SHA256 signature verification
- **Reports**: Transaction summaries and merchant settlement calculations
- **Background Tasks**: Async webhook delivery and settlement computation

## Setup

```bash
pip install -e '.[dev]'
```

## Run

```bash
uvicorn app.main:app --reload
```

## Test

```bash
pytest --cov=app
```

## Architecture

- FastAPI + SQLAlchemy (async) + SQLite (aiosqlite)
- Pydantic models for request/response validation
- Background task queue for webhook delivery
- HMAC-SHA256 webhook signature verification

## Known Limitations

- No rate limiting on any endpoint
- Duplicated validation logic between payments and refunds
- Webhook delivery handler has no test coverage
