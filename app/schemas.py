"""Pydantic schemas for request/response validation."""

from pydantic import BaseModel


class UserCreate(BaseModel):
    """Schema for creating a user."""

    name: str
    email: str


class UserResponse(BaseModel):
    """Schema for user responses."""

    id: int
    name: str
    email: str

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    """Schema for creating a task."""

    title: str
    description: str = ""
    owner_id: int


class TaskUpdate(BaseModel):
    """Schema for updating a task."""

    title: str | None = None
    description: str | None = None
    done: bool | None = None


class TaskResponse(BaseModel):
    """Schema for task responses."""

    id: int
    title: str
    description: str
    done: bool
    owner_id: int

    model_config = {"from_attributes": True}
