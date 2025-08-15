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
    BookCreate,
    BookResponse,
    UserCreate,
    UserResponse,
    BookshelfResponse,
    BookshelfEntry,
    ReadingListResponse,
    ReadingListBookEntry,
)
from app.models import Bookshelf
from datetime import datetime, timezone
from fastapi import Body, Path
from app.openlibrary import search_openlibrary
from async_lru import alru_cache


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


def dont_allow_empty_user(username):
    if not username or username.strip() == "":
        raise HTTPException(
            status_code=400, detail="You must provide a non-empty username."
        )


@alru_cache(maxsize=64)
async def cached_search_openlibrary(title_or_author, author, limit):
    return await search_openlibrary(title_or_author, author, limit)


@app.get("/books/search")
async def get_book_by_name_or_author(
    title: Optional[str] = Query(None, description="Book title"),
    author: Optional[str] = Query(None, description="Author name"),
    limit: int = Query(5, ge=1, le=20, description="Max results"),
    external: bool = Query(
        False, description="Search on Open Library if true."
    ),
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

        return {
            "local": local_results,
            "external": external_results,
        }
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


@app.delete("/books/{id}", response_model=BookResponse)
def delete_book(
    id: int = Path(..., description="Book ID"),
    db: Session = Depends(get_db),
):

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


@app.get("/users", response_model=list[UserResponse])
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


@app.get("/users/search", response_model=UserResponse)
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


@app.post("/users", response_model=UserResponse)
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

        now = datetime.now(timezone.utc)
        db_user = models.User(
            username=user.username,
            email=user.email,
            created_at=now,
            updated_at=now,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
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


@app.put("/users/{id}", response_model=UserResponse)
def update_user(
    id: int,
    user_update: UserCreate,
    db: Session = Depends(get_db),
):
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
):
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
    username: str = Query(..., description="Username"), db: Session = Depends(get_db)
):
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
):

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


@app.post("/users/readinglists", response_model=ReadingListResponse)
def create_reading_list(
    username: str = Query(..., description="Username"),
    name: str = Query(..., description="Reading list name"),
    db: Session = Depends(get_db),
):

    dont_allow_empty_user(username)
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    count = (
        db.query(models.ReadingList)
        .filter(models.ReadingList.user_id == user.id)
        .count()
    )
    if count >= 3:
        raise HTTPException(
            status_code=400, detail="User can have 3 reading lists simultaneously."
        )

    existing = (
        db.query(models.ReadingList)
        .filter(
            models.ReadingList.user_id == user.id, models.ReadingList.list_name == name
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Reading list with this name already exists."
        )

    reading_list = models.ReadingList(user_id=user.id, list_name=name)
    db.add(reading_list)
    db.commit()
    db.refresh(reading_list)

    return ReadingListResponse(
        id=reading_list.id,
        username=user.username,
        reading_list_name=reading_list.list_name,
        books=[],
    )


@app.get("/user/readinglists/", response_model=list[ReadingListResponse])
def get_reading_lists(
    username: str = Query(..., description="Username"), db: Session = Depends(get_db)
):
    dont_allow_empty_user(username)
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    reading_lists = (
        db.query(models.ReadingList).filter(models.ReadingList.user_id == user.id).all()
    )

    result = []

    for rl in reading_lists:
        books = [
            ReadingListBookEntry(
                id=book.id,
                book_id=book.id,
                title=book.title,
                author=book.author,
            )
            for book in rl.books
        ]
        result.append(
            ReadingListResponse(
                id=rl.id,
                username=user.username,
                reading_list_name=rl.list_name,
                books=books,
            )
        )
    return result


@app.delete("/users/readinglists/{name}", response_model=ReadingListResponse)
def delete_reading_list(
    username: str = Query(..., description="Username"),
    name: str = Path(..., description="Reading list name"),
    db: Session = Depends(get_db),
):
    dont_allow_empty_user(username)
    if not name or name.strip() == "":
        raise HTTPException(
            status_code=400, detail="You must provide a non-empty reading list name."
        )

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    reading_list = (
        db.query(models.ReadingList)
        .filter(
            models.ReadingList.user_id == user.id, models.ReadingList.list_name == name
        )
        .first()
    )
    if not reading_list:
        raise HTTPException(status_code=404, detail="Reading list not found.")

    books = [
        ReadingListBookEntry(
            id=book.id,
            book_id=book.id,
            title=book.title,
            author=book.author,
        )
        for book in reading_list.books
    ]
    response = ReadingListResponse(
        id=reading_list.id,
        username=user.username,
        reading_list_name=reading_list.list_name,
        books=books,
    )

    try:
        db.delete(reading_list)
        db.commit()
        return response
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
