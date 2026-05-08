"""Tests for user routes."""


def test_create_user(client):
    """Creating a user returns 201 with the user data."""
    response = client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Alice"
    assert data["email"] == "alice@example.com"
    assert "id" in data


def test_create_user_duplicate_email(client):
    """Creating a user with a duplicate email returns 409."""
    client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    response = client.post("/users/", json={"name": "Bob", "email": "alice@example.com"})
    assert response.status_code == 409


def test_list_users(client):
    """Listing users returns all created users."""
    client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    client.post("/users/", json={"name": "Bob", "email": "bob@example.com"})
    response = client.get("/users/")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_user(client):
    """Getting a user by ID returns the user."""
    create_resp = client.post("/users/", json={"name": "Alice", "email": "alice@example.com"})
    user_id = create_resp.json()["id"]
    response = client.get(f"/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Alice"


def test_get_user_not_found(client):
    """Getting a non-existent user returns 404."""
    response = client.get("/users/999")
    assert response.status_code == 404
