from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command
from app.database import engine, Base, get_db
from app import models
from sqlalchemy import or_
from app.schemas import (
    UserCreate,
    UserResponse,
    BookshelfResponse,
    BookshelfEntry,
)
from app.models import Bookshelf
from datetime import datetime, timezone
from fastapi import Body, Path, status
from async_lru import alru_cache
import logging
from fastapi.security import OAuth2PasswordRequestForm
from app.auth import (
    authenticate_user,
    create_access_token,
    get_password_hash,
    get_current_user,
)
from app.routers import reading_list_router
from app.routers import book_router
from app.openlibrary import search_openlibrary


@asynccontextmanager
async def lifespan(app: FastAPI):
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield


app = FastAPI(lifespan=lifespan, title="Library api")
app.include_router(reading_list_router.router)
app.include_router(book_router.router)

Base.metadata.create_all(bind=engine)


def find_user_by_username_or_email(
    db: Session, username: Optional[str], email: Optional[str]
):
    """
    Helper function to find a user by username and/or email.
    """
    query = db.query(models.User)
    if username and email:
        return query.filter(
            models.User.username == username, models.User.email == email
        ).first()
    elif username:
        return query.filter(models.User.username == username).first()
    elif email:
        return query.filter(models.User.email == email).first()
    return None


def dont_allow_empty_user(username):
    if not username or username.strip() == "":
        raise HTTPException(
            status_code=400, detail="You must provide a non-empty username."
        )


@alru_cache(maxsize=64)
async def cached_search_openlibrary(title_or_author, author, limit):
    return await search_openlibrary(title_or_author, author, limit)


@app.post("/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    if not form_data.username or form_data.username.strip() == "":
        raise HTTPException(status_code=400, detail="Username cannot be empty or whitespace.")
    if not form_data.password or form_data.password.strip() == "":
        raise HTTPException(status_code=400, detail="Password cannot be empty or whitespace.")

    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    """User registration endpoint."""
    if not user.username or user.username.strip() == "":
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    if not user.email or user.email.strip() == "":
        raise HTTPException(status_code=400, detail="Email cannot be empty.")
    if not user.password or user.password.strip() == "":
        raise HTTPException(status_code=400, detail="Password cannot be empty.")

    username_exists = (
        db.query(models.User).filter(models.User.username == user.username).first()
    )
    email_exists = db.query(models.User).filter(models.User.email == user.email).first()

    if username_exists:
        raise HTTPException(status_code=400, detail="Username already exists.")
    if email_exists:
        raise HTTPException(status_code=400, detail="Email already exists.")

    hashed_password = get_password_hash(user.password)
    now = datetime.now(timezone.utc)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        created_at=now,
        updated_at=now,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.get("/cache/openlibrary/info")
async def get_openlibrary_cache_info():
    """Get cache statistics for the OpenLibrary search cache."""
    try:
        info = cached_search_openlibrary.cache_info()  # <-- no await here
        return {k: getattr(info, k) for k in info._fields}
    except Exception as e:
        logging.exception("Error getting cache info")
        raise HTTPException(status_code=500, detail=f"Cache error: {str(e)}")


@app.post("/cache/openlibrary/clear")
async def clear_openlibrary_cache():
    """Clear the OpenLibrary search cache."""
    await cached_search_openlibrary.cache_clear()
    return {"detail": "Cache cleared."}


@app.get("/users", response_model=list[UserResponse])
def get_all_users(
    page: int = Query(..., gt=0, description="Page number"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Retrieve a paginated list of all users.
    """
    try:
        page_size = 20
        offset = (page - 1) * page_size
        users = db.query(models.User).offset(offset).limit(page_size).all()
        return users
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/users/search", response_model=UserResponse)
def get_user(
    username: Optional[str] = Query(None, description="Username"),
    email: Optional[str] = Query(None, description="Email"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ "
    Search user by name or email.
    """
    if (not username or username.strip() == "") and (not email or email.strip() == ""):
        raise HTTPException(
            status_code=400, detail="You must provide a non-empty username or email."
        )
    try:
        user = find_user_by_username_or_email(db, username, email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        return user
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.delete("/users", response_model=UserResponse)
def delete_user(
    username: Optional[str] = Query(None, description="Username"),
    email: Optional[str] = Query(None, description="Email"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ "
    Delete user by id.
    """
    if (not username or username.strip() == "") and (not email or email.strip() == ""):
        raise HTTPException(
            status_code=400, detail="You must provide a non-empty username or email."
        )
    try:
        user = find_user_by_username_or_email(db, username, email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        db.delete(user)
        db.commit()
        return user
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.put("/users/{id}", response_model=UserResponse)
def update_user(
    id: int,
    user_update: UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ "
    Update user by id.
    """
    user = db.query(models.User).filter(models.User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user_update.username != user.username:
        if (
            db.query(models.User)
            .filter(models.User.username == user_update.username)
            .first()
        ):
            raise HTTPException(status_code=400, detail="Username already exists.")
    if user_update.email != user.email:
        if db.query(models.User).filter(models.User.email == user_update.email).first():
            raise HTTPException(status_code=400, detail="Email already exists.")

    user.username = user_update.username
    user.email = user_update.email
    user.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)
    return user


@app.post("/users/bookshelf", response_model=BookshelfResponse)
def add_book_to_bookshelf(
    username: str = Query(..., description="Username"),
    book_id: int = Query(..., description="Book ID"),
    status: str = Query("to_read", description="Reading status"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Bookshelf creation using book and statuses.
    """
    dont_allow_empty_user(username)

    if not status or status.strip() == "":
        raise HTTPException(
            status_code=400, detail="Status cannot be blank or whitespace."
        )
    if status not in Bookshelf.READING_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    book = db.query(models.Book).filter(models.Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")

    existing = (
        db.query(Bookshelf)
        .filter(Bookshelf.user_id == user.id, Bookshelf.book_id == book.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Book already in user's bookshelf.")

    added_date = datetime.now(timezone.utc).date()

    bookshelf_entry = Bookshelf(
        user_id=user.id,
        book_id=book.id,
        status=status,
        date_added=added_date,
    )
    db.add(bookshelf_entry)
    db.commit()
    db.refresh(bookshelf_entry)

    bookshelf = [
        {
            "id": bookshelf_entry.id,
            "book_id": book.id,
            "title": book.title,
            "author": book.author,
            "status": bookshelf_entry.status,
            "added_date": bookshelf_entry.date_added,
        }
    ]

    return {"username": user.username, "bookshelf": bookshelf}


@app.get("/users/bookshelf", response_model=BookshelfResponse)
def get_user_bookshelf(
    username: str = Query(..., description="Username"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ "
    Get user bookshelf data list.
    """
    dont_allow_empty_user(username)

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    bookshelf_entries = (
        db.query(models.Bookshelf).filter(models.Bookshelf.user_id == user.id).all()
    )
    bookshelf = [
        {
            "id": entry.id,
            "book_id": entry.book.id,
            "title": entry.book.title,
            "author": entry.book.author,
            "status": entry.status,
            "added_date": entry.date_added,
        }
        for entry in bookshelf_entries
    ]
    return {"username": user.username, "bookshelf": bookshelf}


@app.put("/users/bookshelf", response_model=BookshelfResponse)
def update_bookshelf_status(
    username: str = Query(..., description="Username"),
    book_id: int = Query(..., description="Book ID"),
    new_status: str = Body(..., embed=True, description="New reading status"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ "
    Update bookshelf by user id.
    """

    dont_allow_empty_user(username)

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    bookshelf_entry = (
        db.query(Bookshelf)
        .filter(Bookshelf.user_id == user.id, Bookshelf.book_id == book_id)
        .first()
    )
    if not bookshelf_entry:
        raise HTTPException(
            status_code=404, detail="Book not found in user's bookshelf."
        )

    if new_status not in Bookshelf.READING_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

    bookshelf_entry.status = new_status
    db.commit()
    db.refresh(bookshelf_entry)

    bookshelf_entries = (
        db.query(models.Bookshelf).filter(models.Bookshelf.user_id == user.id).all()
    )
    bookshelf = [
        BookshelfEntry(
            id=entry.id,
            book_id=entry.book.id,
            title=entry.book.title,
            author=entry.book.author,
            status=entry.status,
            added_date=(entry.date_added.date() if entry.date_added else None),
        )
        for entry in bookshelf_entries
    ]
    return BookshelfResponse(username=user.username, bookshelf=bookshelf)
