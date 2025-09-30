from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command
from app.database import engine, Base, get_db
from app import models
from app.schemas import (
    UserCreate,
    UserResponse,
)
from datetime import datetime, timezone
from fastapi import status
from async_lru import alru_cache
import logging
from fastapi.security import OAuth2PasswordRequestForm
from app.auth import (
    authenticate_user,
    create_access_token,
    get_password_hash,
)
from app.routers import reading_list_router
from app.routers import book_router
from app.routers import user_router
from app.openlibrary import search_openlibrary


@asynccontextmanager
async def lifespan(app: FastAPI):
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield


app = FastAPI(lifespan=lifespan, title="Library api")
app.include_router(reading_list_router.router)
app.include_router(book_router.router)
app.include_router(user_router.router)

Base.metadata.create_all(bind=engine)

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