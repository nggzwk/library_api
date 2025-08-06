from typing import Union, Optional
from datetime import datetime, date
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from alembic.config import Config
from alembic import command
from app.database import engine, Base, get_db
from app import models

@asynccontextmanager
async def lifespan(app: FastAPI):
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield

app = FastAPI(lifespan=lifespan, title='Library api')

Base.metadata.create_all(bind=engine)


class BookCreate(BaseModel):
    title: str
    author: str
    isbn: str
    genre: str
    description: str
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

@app.get("/books/{id}")
def get_book(id: int):
    return {"id": id}

@app.get("/books")
def get_all_books():
    return {"books": []}

@app.post("/books", response_model=BookResponse)
def create_a_book(book: BookCreate, db: Session = Depends(get_db)):
    try:
        existing_book = db.query(models.Book).filter(models.Book.isbn == book.isbn).first()
        if existing_book:
            raise HTTPException(status_code=400, detail=f"Book with ISBN {book.isbn} already exists")
            
        db_book = models.Book(
            title=book.title,
            author=book.author,
            isbn=book.isbn,
            genre=book.genre,
            description=book.description,
            published_date=book.published_date
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