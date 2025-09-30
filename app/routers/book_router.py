from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app import models
from app.schemas import BookCreate, BookResponse
from app.openlibrary import search_openlibrary
from async_lru import alru_cache
from app.auth import get_current_user

router = APIRouter(prefix="/books", tags=["books"])

@alru_cache(maxsize=64)
async def cached_search_openlibrary(title_or_author, author, limit):
    return await search_openlibrary(title_or_author, author, limit)

@router.get("/search")
async def get_book_by_name_or_author(
    title: Optional[str] = Query(None, description="Book title"),
    author: Optional[str] = Query(None, description="Author name"),
    limit: int = Query(5, ge=1, le=20, description="Max results"),
    external: bool = Query(False, description="Search on Open Library if true."),
    db: Session = Depends(get_db),
):
    """
    Search for books by title or author.
    Also searchs on Open Library Api if true.
    """
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

        local_results = [
            BookResponse.model_validate(book).model_dump() for book in books
        ]

        external_results = []
        if external:
            data = await cached_search_openlibrary(title or author, author, limit)
            for doc in data.get("docs", []):
                external_results.append(
                    {
                        "title": doc.get("title"),
                        "author": (
                            ", ".join(doc.get("author_name", []))
                            if doc.get("author_name")
                            else None
                        ),
                        "isbn": doc.get("isbn", [None])[0] if doc.get("isbn") else None,
                        "genre": (
                            ", ".join(doc.get("subject", []))
                            if doc.get("subject")
                            else None
                        ),
                        "published_date": doc.get("first_publish_year"),
                    }
                )

        if not local_results and not external:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "No data found locally.",
                    "local": [],
                    "external": [],
                },
            )

        return {
            "local": local_results,
            "external": external_results,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("", response_model=list[BookResponse])
def get_all_books(
    page: int = Query(..., gt=0, description="Page number"),
    db: Session = Depends(get_db),
):
    """
    Get all locally stored books.
    """
    try:
        page_size = 20
        offset = (page - 1) * page_size
        books = db.query(models.Book).offset(offset).limit(page_size)
        return books
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("", response_model=BookResponse)
def create_book(
    book: BookCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Create a book to be stored locally.
    """
    for field_name in ["title", "author", "isbn", "genre", "description"]:
        value = getattr(book, field_name)
        if not value or value.strip() == "":
            raise HTTPException(
                status_code=400,
                detail=f"{field_name.capitalize()} cannot be empty or whitespace.",
            )
    try:
        existing_book = (
            db.query(models.Book)
            .filter((models.Book.isbn == book.isbn) | (models.Book.title == book.title))
            .first()
        )
        if existing_book:
            raise HTTPException(
                status_code=400,
                detail=f"Book with ISBN '{book.isbn}' or title '{book.title}' already exists",
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

@router.delete("/{id}", response_model=BookResponse)
def delete_book(
    id: int = Path(..., description="Book ID"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Delete locally stored book by its ID.
    """
    try:
        book_to_delete = db.query(models.Book).filter(models.Book.id == id).first()
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