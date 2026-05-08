"""Task routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Task, User
from app.schemas import TaskCreate, TaskUpdate, TaskResponse

router = APIRouter()


@router.get("/", response_model=list[TaskResponse])
def list_tasks(db: Session = Depends(get_db)):
    """List all tasks."""
    return db.query(Task).all()


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    """Get a task by ID."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/", response_model=TaskResponse, status_code=201)
def create_task(task_in: TaskCreate, db: Session = Depends(get_db)):
    """Create a new task."""
    owner = db.query(User).filter(User.id == task_in.owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    task = Task(
        title=task_in.title,
        description=task_in.description,
        owner_id=task_in.owner_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task_in: TaskUpdate, db: Session = Depends(get_db)):
    """Update a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task_in.title is not None:
        task.title = task_in.title
    if task_in.description is not None:
        task.description = task_in.description
    if task_in.done is not None:
        task.done = task_in.done
    db.commit()
    db.refresh(task)
    return task
