from typing import Union, Optional
from datetime import datetime, date
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from alembic.config import Config
from alembic import command
from app.database import engine, Base, get_db
from app import models
from sqlalchemy import or_
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder


@asynccontextmanager
async def lifespan(app: FastAPI):
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield


app = FastAPI(lifespan=lifespan, title="Library api")

Base.metadata.create_all(bind=engine)


class BookCreate(BaseModel):
    title: str = Field(..., min_length=1)
    author: str = Field(..., min_length=1)
    isbn: str = Field(..., min_length=1)
    genre: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    published_date: Optional[date] = None


class BookResponse(BaseModel):
    id: int
    title: str
    author: str
    isbn: str
    genre: str
    description: str
    published_date: Optional[date] = None

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str

    class Config:
        from_attributes = True


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





# get bookshelf
# @app.get("/bookshelf", response_model=BookResponse)


# post user
# get user
# delete user
# post reading list
# get reading list
# delete reading list
