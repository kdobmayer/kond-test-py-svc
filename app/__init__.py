"""FastAPI application factory."""

from fastapi import FastAPI

from app.database import engine, Base
from app.routes import users, tasks


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    Base.metadata.create_all(bind=engine)

    application = FastAPI(
        title="Task Service",
        description="A simple task and user management service.",
        version="0.1.0",
    )

    application.include_router(users.router, prefix="/users", tags=["users"])
    application.include_router(tasks.router, prefix="/tasks", tags=["tasks"])

    return application


app = create_app()
