from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.schemas import ReadingListResponse, ReadingListBookEntry
from app.auth import get_current_user

router = APIRouter(prefix="/users", tags=["reading-lists"])


def dont_allow_empty_user(username):
    if not username or username.strip() == "":
        raise HTTPException(
            status_code=400, detail="You must provide a non-empty username."
        )


@router.post("/readinglists", response_model=ReadingListResponse)
def create_reading_list(
    username: str = Query(..., description="Username"),
    name: str = Query(..., description="Reading list name"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Create readinglist by book id.
    """
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


@router.get("/readinglists/", response_model=list[ReadingListResponse])
def get_reading_lists(
    username: str = Query(..., description="Username"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Get users readinglists by username.
    """
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


@router.delete("/readinglists/{name}", response_model=ReadingListResponse)
def delete_reading_list(
    username: str = Query(..., description="Username"),
    name: str = Path(..., description="Reading list name"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Delete reading list by name.
    """
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