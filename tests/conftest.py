"""Test fixtures."""

import os
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import create_app
from app.database import Base, get_db

TEST_JWT_SECRET = "testsecret"


TEST_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def set_jwt_secret():
    """Set JWT_SECRET environment variable for all tests."""
    os.environ["JWT_SECRET"] = TEST_JWT_SECRET
    yield
    os.environ.pop("JWT_SECRET", None)


@pytest.fixture
def valid_token() -> str:
    """Return a valid JWT for alice@example.com signed with the test secret."""
    payload = {"sub": "alice@example.com", "exp": int(time.time()) + 3600}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    """Provide a test database session."""
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    """Provide a test client with overridden DB dependency."""
    application = create_app()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    application.dependency_overrides[get_db] = override_get_db
    return TestClient(application)
