"""Tests for task routes."""


def test_create_task(client):
    """Creating a task returns 201 with the task data."""
    user_resp = client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    user_id = user_resp.json()["id"]
    response = client.post("/tasks/", json={"title": "Buy milk", "owner_id": user_id})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Buy milk"
    assert data["done"] is False
    assert data["owner_id"] == user_id


def test_create_task_owner_not_found(client):
    """Creating a task with a non-existent owner returns 404."""
    response = client.post("/tasks/", json={"title": "Buy milk", "owner_id": 999})
    assert response.status_code == 404


def test_list_tasks(client):
    """Listing tasks returns all created tasks."""
    user_resp = client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    user_id = user_resp.json()["id"]
    client.post("/tasks/", json={"title": "Task 1", "owner_id": user_id})
    client.post("/tasks/", json={"title": "Task 2", "owner_id": user_id})
    response = client.get("/tasks/")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_task(client):
    """Getting a task by ID returns the task."""
    user_resp = client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    user_id = user_resp.json()["id"]
    create_resp = client.post("/tasks/", json={"title": "Buy milk", "owner_id": user_id})
    task_id = create_resp.json()["id"]
    response = client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Buy milk"


def test_get_task_not_found(client):
    """Getting a non-existent task returns 404."""
    response = client.get("/tasks/999")
    assert response.status_code == 404


def test_update_task(client):
    """Updating a task changes the specified fields."""
    user_resp = client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    user_id = user_resp.json()["id"]
    create_resp = client.post("/tasks/", json={"title": "Buy milk", "owner_id": user_id})
    task_id = create_resp.json()["id"]
    response = client.patch(f"/tasks/{task_id}", json={"done": True})
    assert response.status_code == 200
    assert response.json()["done"] is True
    assert response.json()["title"] == "Buy milk"


def test_update_task_not_found(client):
    """Updating a non-existent task returns 404."""
    response = client.patch("/tasks/999", json={"done": True})
    assert response.status_code == 404
