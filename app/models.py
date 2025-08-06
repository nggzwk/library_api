from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Float,
    Table,
    CheckConstraint,
    Date
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base

reading_list_books = Table(
    "reading_list_books",
    Base.metadata,
    Column(
        "reading_list_id", Integer, ForeignKey("reading_lists.id"), primary_key=True
    ),
    Column("book_id", Integer, ForeignKey("books.id"), primary_key=True),
    Column("date_added", DateTime, default=lambda: datetime.now(timezone.utc)),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    bookshelf_entries = relationship("Bookshelf", back_populates="user")
    reading_lists = relationship("ReadingList", back_populates="user")


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), index=True, nullable=False)
    author = Column(String(255), index=True, nullable=False)
    isbn = Column(String(13), unique=True, index=True, nullable=False)
    genre = Column(String(100), index=True)
    published_date = Column(Date)
    public_rating = Column(Float)
    description = Column(String(2000))

    # Relationships
    bookshelf_entries = relationship("Bookshelf", back_populates="book")
    reading_lists = relationship(
        "ReadingList", secondary=reading_list_books, back_populates="books"
    )


class Bookshelf(Base):
    """
    Represents individual book entries in an user's bookshelf.
    Each user has one conceptual bookshelf containing multiple book entries.
    """

    __tablename__ = "bookshelves"

    READING_STATUSES = ["to_read", "reading", "read", "abandoned"]

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    book_id = Column(Integer, ForeignKey("books.id"), index=True, nullable=False)
    status = Column(String(20), index=True, nullable=False)
    personal_rating = Column(Integer)
    review = Column(String(2000))
    date_added = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(
            "personal_rating >= 1 AND personal_rating <= 5", name="check_rating_range"
        ),
        CheckConstraint(
            "status IN ('to_read', 'reading', 'read', 'abandoned')",
            name="check_status_values",
        ),
    )

    # Relationships
    user = relationship("User", back_populates="bookshelf_entries")
    book = relationship("Book", back_populates="bookshelf_entries")


class ReadingList(Base):
    """
    Represents a named reading list created by an user.
    Each list can contain multiple books via the association table.
    """

    __tablename__ = "reading_lists"

    id = Column(Integer, primary_key=True, index=True)
    list_name = Column(String(255), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", back_populates="reading_lists")
    books = relationship(
        "Book", secondary=reading_list_books, back_populates="reading_lists"
    )
