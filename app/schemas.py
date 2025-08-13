from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator

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
    username: str = Field(..., min_length=5)
    email: str = Field(..., min_length=1)

    @field_validator("username")
    @classmethod
    def no_blank_spaces_username(cls, v):
        if not v or v.strip() == "":
            raise ValueError("Username cannot be empty or whitespace.")
        return v

    @field_validator("email")
    @classmethod
    def no_blank_spaces_and_at(cls, v):
        if not v or v.strip() == "":
            raise ValueError("Email cannot be empty or whitespace.")
        if "@" not in v:
            raise ValueError("Email must contain '@'.")
        return v

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    updated_at: Optional[datetime] = None


    class Config:
        from_attributes = True

class BookshelfEntry(BaseModel):
    id: int
    book_id: int
    title: str
    author: str
    status: str
    added_date: date

class BookshelfResponse(BaseModel):
    username: str
    bookshelf: list[BookshelfEntry]


class ReadingListCreate(BaseModel):
    name: str = Field(..., min_length=1)

class ReadingListBookEntry(BaseModel):
    id: int
    book_id: int
    title: str
    author: str

class ReadingListResponse(BaseModel):
    id: int
    username: str
    reading_list_name: str
    books: List[ReadingListBookEntry] = []

    class Config:
        from_attributes = True