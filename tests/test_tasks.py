"""Tests for task routes."""

import time

from jose import jwt


def test_create_task(client, valid_token):
    """Creating a task returns 201 with the task data owned by the authenticated user."""
    user_resp = client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    user_id = user_resp.json()["id"]
    response = client.post(
        "/tasks/",
        json={"title": "Buy milk"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Buy milk"
    assert data["done"] is False
    assert data["owner_id"] == user_id


def test_create_task_unknown_user_returns_401(client):
    """Creating a task when the token sub has no matching user returns 401."""
    token = jwt.encode(
        {"sub": "nobody@example.com", "exp": int(time.time()) + 3600},
        "testsecret",
        algorithm="HS256",
    )
    response = client.post(
        "/tasks/",
        json={"title": "Buy milk"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_list_tasks(client, valid_token):
    """Listing tasks returns all created tasks."""
    client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    client.post(
        "/tasks/",
        json={"title": "Task 1"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    client.post(
        "/tasks/",
        json={"title": "Task 2"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    response = client.get("/tasks/")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_task(client, valid_token):
    """Getting a task by ID returns the task."""
    client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    create_resp = client.post(
        "/tasks/",
        json={"title": "Buy milk"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    task_id = create_resp.json()["id"]
    response = client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Buy milk"


def test_get_task_not_found(client):
    """Getting a non-existent task returns 404."""
    response = client.get("/tasks/999")
    assert response.status_code == 404


def test_update_task(client, valid_token):
    """Updating a task changes the specified fields."""
    client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    create_resp = client.post(
        "/tasks/",
        json={"title": "Buy milk"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    task_id = create_resp.json()["id"]
    response = client.patch(
        f"/tasks/{task_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    assert response.json()["done"] is True
    assert response.json()["title"] == "Buy milk"


def test_update_task_not_found(client, valid_token):
    """Updating a non-existent task returns 404."""
    client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    response = client.patch(
        "/tasks/999",
        json={"done": True},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 404
