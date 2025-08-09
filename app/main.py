from typing import Union, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command
from app.database import engine, Base, get_db
from app import models
from sqlalchemy import or_
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from app.schemas import BookCreate, BookResponse, UserCreate, UserResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield


app = FastAPI(lifespan=lifespan, title="Library api")

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


@app.get("/books/search")
def get_book_by_name_or_author(
    title: Optional[str] = Query(None, description="Book title"),
    author: Optional[str] = Query(None, description="Author name"),
    db: Session = Depends(get_db),
):
    if (title is None or title.strip() == "") and (
        author is None or author.strip() == ""
    ):
        raise HTTPException(
            status_code=400,
            detail="You must provide at least a non-empty title or author.",
        )
    try:
        query = db.query(models.Book)
        if title and author:
            query = query.filter(
                or_(models.Book.title == title, models.Book.author == author)
            )
        elif title:
            query = query.filter(models.Book.title == title)
        elif author:
            query = query.filter(models.Book.author == author)
        books = query.all()
        if not books:
            raise HTTPException(
                status_code=404, detail="Bad request, book or author not registered."
            )

        title_books = [book for book in books if title and book.title == title]
        author_books = [book for book in books if author and book.author == author]

        response_content = {
            "title": [
                BookResponse.model_validate(book).model_dump() for book in title_books
            ],
            "author": [
                BookResponse.model_validate(book).model_dump() for book in author_books
            ],
        }
        return JSONResponse(content=jsonable_encoder(response_content))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/books", response_model=list[BookResponse])
def get_all_books(
    page: int = Query(..., gt=0, description="Page number"),
    db: Session = Depends(get_db),
):
    try:
        page_size = 20
        offset = (page - 1) * page_size
        books = db.query(models.Book).offset(offset).limit(page_size)
        return books
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.post("/books", response_model=BookResponse)
def create_book(book: BookCreate, db: Session = Depends(get_db)):
    for field_name in ["title", "author", "isbn", "genre", "description"]:
        value = getattr(book, field_name)
        if not value or value.strip() == "":
            raise HTTPException(
                status_code=400,
                detail=f"{field_name.capitalize()} cannot be empty or whitespace.",
            )
    try:
        existing_book = (
            db.query(models.Book).filter(models.Book.isbn == book.isbn).first()
        )
        if existing_book:
            raise HTTPException(
                status_code=400, detail=f"Book with ISBN {book.isbn} already exists"
            )

        db_book = models.Book(
            title=book.title,
            author=book.author,
            isbn=book.isbn,
            genre=book.genre,
            description=book.description,
            published_date=book.published_date,
        )
        db.add(db_book)
        db.commit()
        db.refresh(db_book)
        return db_book
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.delete("/books/{title}", response_model=BookResponse)
def delete_book(
    title: str,
    db: Session = Depends(get_db),
):
    if title.strip() == "":
        raise HTTPException(
            status_code=400, detail="Title cannot be blank or whitespace."
        )
    try:
        book_to_delete = (
            db.query(models.Book).filter(models.Book.title == title).first()
        )
        if not book_to_delete:
            raise HTTPException(status_code=404, detail="Book not found.")
        db.delete(book_to_delete)
        db.commit()
        return book_to_delete
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.post("/user", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    if not user.username or user.username.strip() == "":
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    if not user.email or user.email.strip() == "":
        raise HTTPException(status_code=400, detail="Email cannot be empty.")

    try:
        username_exists = (
            db.query(models.User).filter(models.User.username == user.username).first()
        )
        email_exists = (
            db.query(models.User).filter(models.User.email == user.email).first()
        )

        if username_exists and email_exists:
            raise HTTPException(
                status_code=400,
                detail="A user with this username and email already exists.",
            )
        elif username_exists:
            raise HTTPException(
                status_code=400,
                detail="A user with this username already exists.",
            )
        elif email_exists:
            raise HTTPException(
                status_code=400,
                detail="A user with this email already exists.",
            )

        db_user = models.User(username=user.username, email=user.email)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/user/search", response_model=UserResponse)
def get_user(
    username: Optional[str] = Query(None, description="Username"),
    email: Optional[str] = Query(None, description="Email"),
    db: Session = Depends(get_db),
):
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


@app.delete("/user", response_model=UserResponse)
def delete_user(
    username: Optional[str] = Query(None, description="Username"),
    email: Optional[str] = Query(None, description="Email"),
    db: Session = Depends(get_db),
):
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


@app.get("/user", response_model=list[UserResponse])
def get_all_users(
    page: int = Query(..., gt=0, description="Page number"),
    db: Session = Depends(get_db),
):
    try:
        page_size = 20
        offset = (page - 1) * page_size
        users = db.query(models.User).offset(offset).limit(page_size)
        return users
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# get bookshelf
# @app.get("/bookshelf", response_model=BookResponse)
# post reading list
# get reading list
# delete reading list