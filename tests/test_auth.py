"""Tests for JWT authentication on task routes."""

import time

import pytest
from jose import jwt

TEST_JWT_SECRET = "testsecret"


def _expired_token() -> str:
    payload = {"sub": "alice@example.com", "exp": int(time.time()) - 1}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def _token_for(email: str) -> str:
    payload = {"sub": email, "exp": int(time.time()) + 3600}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def _create_user_and_task(client, valid_token: str) -> tuple[int, int]:
    user_id = client.post("/users/", json={"name": "Alice", "email": "alice@example.com"}).json()["id"]
    task_id = client.post(
        "/tasks/",
        json={"title": "Test Task"},
        headers={"Authorization": f"Bearer {valid_token}"},
    ).json()["id"]
    return user_id, task_id


# --- POST /tasks/ auth cases ---


def test_create_task_valid_token(client, valid_token):
    """Valid JWT allows creating a task."""
    client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    response = client.post(
        "/tasks/",
        json={"title": "Test Task"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 201


def test_create_task_missing_header_returns_401(client):
    """Missing Authorization header on POST /tasks/ returns 401."""
    response = client.post("/tasks/", json={"title": "Test Task"})
    assert response.status_code == 401
    assert "detail" in response.json()


def test_create_task_expired_token_returns_401(client):
    """Expired JWT on POST /tasks/ returns 401."""
    response = client.post(
        "/tasks/",
        json={"title": "Test Task"},
        headers={"Authorization": f"Bearer {_expired_token()}"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_create_task_malformed_token_returns_401(client):
    """Malformed JWT on POST /tasks/ returns 401."""
    response = client.post(
        "/tasks/",
        json={"title": "Test Task"},
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_create_task_token_missing_sub_returns_401(client):
    """JWT without a 'sub' claim on POST /tasks/ returns 401."""
    token = jwt.encode({"exp": int(time.time()) + 3600}, TEST_JWT_SECRET, algorithm="HS256")
    response = client.post(
        "/tasks/",
        json={"title": "Test Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_create_task_token_missing_exp_returns_401(client):
    """JWT without an 'exp' claim on POST /tasks/ returns 401."""
    token = jwt.encode({"sub": "alice@example.com"}, TEST_JWT_SECRET, algorithm="HS256")
    response = client.post(
        "/tasks/",
        json={"title": "Test Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_create_task_assigns_to_authenticated_user(client, valid_token):
    """Task is always owned by the token's user regardless of any owner hint in the body."""
    alice_id = client.post("/users/", json={"name": "Alice", "email": "alice@example.com"}).json()["id"]
    bob_id = client.post("/users/", json={"name": "Bob", "email": "bob@example.com"}).json()["id"]
    # Authenticate as Alice but pass Bob's id in the body
    response = client.post(
        "/tasks/",
        json={"title": "Test Task", "owner_id": bob_id},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 201
    assert response.json()["owner_id"] == alice_id
    assert response.json()["owner_id"] != bob_id


# --- PATCH /tasks/{id} auth cases ---


def test_update_task_valid_token(client, valid_token):
    """Valid JWT allows updating a task."""
    _, task_id = _create_user_and_task(client, valid_token)
    response = client.patch(
        f"/tasks/{task_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200


def test_update_task_missing_header_returns_401(client, valid_token):
    """Missing Authorization header on PATCH /tasks/{id} returns 401."""
    _, task_id = _create_user_and_task(client, valid_token)
    response = client.patch(f"/tasks/{task_id}", json={"done": True})
    assert response.status_code == 401
    assert "detail" in response.json()


def test_update_task_expired_token_returns_401(client, valid_token):
    """Expired JWT on PATCH /tasks/{id} returns 401."""
    _, task_id = _create_user_and_task(client, valid_token)
    response = client.patch(
        f"/tasks/{task_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {_expired_token()}"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_update_task_malformed_token_returns_401(client, valid_token):
    """Malformed JWT on PATCH /tasks/{id} returns 401."""
    _, task_id = _create_user_and_task(client, valid_token)
    response = client.patch(
        f"/tasks/{task_id}",
        json={"done": True},
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_update_task_token_missing_sub_returns_401(client, valid_token):
    """JWT without a 'sub' claim on PATCH /tasks/{id} returns 401."""
    _, task_id = _create_user_and_task(client, valid_token)
    token = jwt.encode({"exp": int(time.time()) + 3600}, TEST_JWT_SECRET, algorithm="HS256")
    response = client.patch(
        f"/tasks/{task_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_update_task_token_missing_exp_returns_401(client, valid_token):
    """JWT without an 'exp' claim on PATCH /tasks/{id} returns 401."""
    _, task_id = _create_user_and_task(client, valid_token)
    token = jwt.encode({"sub": "alice@example.com"}, TEST_JWT_SECRET, algorithm="HS256")
    response = client.patch(
        f"/tasks/{task_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


def test_update_task_by_non_owner_returns_403(client, valid_token):
    """Authenticated user cannot update a task they do not own."""
    _, task_id = _create_user_and_task(client, valid_token)  # Alice's task
    client.post("/users/", json={"name": "Bob", "email": "bob@example.com"})
    bob_token = _token_for("bob@example.com")
    response = client.patch(
        f"/tasks/{task_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert response.status_code == 403
    assert "detail" in response.json()


# --- Unprotected routes require no token ---


def test_list_tasks_no_token(client):
    """GET /tasks/ works without a token."""
    assert client.get("/tasks/").status_code == 200


def test_get_task_no_token(client, valid_token):
    """GET /tasks/{id} works without a token."""
    _, task_id = _create_user_and_task(client, valid_token)
    assert client.get(f"/tasks/{task_id}").status_code == 200


def test_create_user_no_token(client):
    """POST /users/ works without a token."""
    response = client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    assert response.status_code == 201
