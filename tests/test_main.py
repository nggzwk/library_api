import pytest
from unittest.mock import patch, Mock
from fastapi import HTTPException
from datetime import datetime, timezone
from collections import namedtuple


from app.main import (
    cached_search_openlibrary,
    login,
    register_user,
    get_openlibrary_cache_info,
    clear_openlibrary_cache
)

class DummyForm:
    def __init__(self, username, password):
        self.username = username
        self.password = password

@pytest.mark.asyncio
@patch("app.main.search_openlibrary")
async def test_cached_search_openlibrary_returns_result(mock_search):
    mock_search.return_value = [{"title": "Book"}]
    result = await cached_search_openlibrary("Book", "John", 2)
    assert result == [{"title": "Book"}]
    mock_search.assert_awaited_once_with("Book", "John", 2)

@pytest.mark.asyncio
@patch("app.main.search_openlibrary")
async def test_cached_search_openlibrary_caches_result(mock_search):
    mock_search.return_value = [{"title": "Book"}]
    result1 = await cached_search_openlibrary("Book", "John", 2)
    result2 = await cached_search_openlibrary("Book", "John", 2)
    assert result1 == result2
    mock_search.assert_awaited_once()

@pytest.mark.asyncio
@patch("app.main.search_openlibrary")
async def test_cached_search_openlibrary_different_args_not_cached(mock_search):
    mock_search.side_effect = [
        [{"title": "Book1"}],
        [{"title": "Book2"}]
    ]
    result1 = await cached_search_openlibrary("Book", "John", 2)
    result2 = await cached_search_openlibrary("Book", "Jane", 2)
    assert result1 != result2
    assert mock_search.await_count == 2

def test_login_success(monkeypatch):
    mock_db = Mock()
    mock_user = Mock()
    mock_user.username = "user"
    monkeypatch.setattr("app.main.authenticate_user", lambda db, u, p: mock_user)
    monkeypatch.setattr("app.main.create_access_token", lambda data: "token123")

    form = DummyForm("user", "pass")
    result = login(form, mock_db)
    assert result == {"access_token": "token123", "token_type": "bearer"}

@pytest.mark.parametrize(
    "username,password,detail",
    [
        ("", "pass", "Username cannot be empty or whitespace."),
        ("   ", "pass", "Username cannot be empty or whitespace."),
        ("user", "", "Password cannot be empty or whitespace."),
        ("user", "   ", "Password cannot be empty or whitespace."),
    ],
)
def test_login_empty_fields(username, password, detail):
    mock_db = Mock()
    form = DummyForm(username, password)
    with pytest.raises(HTTPException) as exc:
        login(form, mock_db)
    assert exc.value.status_code == 400
    assert exc.value.detail == detail

def test_login_invalid_user(monkeypatch):
    mock_db = Mock()
    monkeypatch.setattr("app.main.authenticate_user", lambda db, u, p: None)
    form = DummyForm("user", "wrongpass")
    with pytest.raises(HTTPException) as exc:
        login(form, mock_db)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Incorrect username or password"

def make_user_create(username="user", email="user@example.com", password="pass"):
    mock_user = Mock()
    mock_user.username = username
    mock_user.email = email
    mock_user.password = password
    return mock_user

def test_register_user_success(monkeypatch):
    mock_db = Mock()
    mock_db.query().filter().first.side_effect = [None, None]
    monkeypatch.setattr("app.main.get_password_hash", lambda pw: "hashed")
    now = datetime.now(timezone.utc)
    mock_user_obj = Mock()
    monkeypatch.setattr("app.main.datetime", Mock(now=Mock(return_value=now)))
    mock_db.add = Mock()
    mock_db.commit = Mock()
    mock_db.refresh = Mock()
    user = make_user_create()

    with patch("app.main.models.User", return_value=mock_user_obj) as user_ctor:
        result = register_user(user, mock_db)
        assert result == mock_user_obj
        mock_db.add.assert_called_once_with(mock_user_obj)
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_user_obj)
        user_ctor.assert_called_once()

@pytest.mark.parametrize(
    "username,email,password,detail",
    [
        ("", "user@example.com", "pass", "Username cannot be empty."),
        ("   ", "user@example.com", "pass", "Username cannot be empty."),
        ("user", "", "pass", "Email cannot be empty."),
        ("user", "   ", "pass", "Email cannot be empty."),
        ("user", "user@example.com", "", "Password cannot be empty."),
        ("user", "user@example.com", "   ", "Password cannot be empty."),
    ],
)
def test_register_user_empty_fields(username, email, password, detail):
    mock_db = Mock()
    user = make_user_create(username=username, email=email, password=password)
    with pytest.raises(HTTPException) as exc:
        register_user(user, mock_db)
    assert exc.value.status_code == 400
    assert exc.value.detail == detail

def test_register_user_username_exists(monkeypatch):
    mock_db = Mock()
    mock_db.query().filter().first.side_effect = [Mock(), None]
    user = make_user_create()
    with pytest.raises(HTTPException) as exc:
        register_user(user, mock_db)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Username already exists."

def test_register_user_email_exists(monkeypatch):
    mock_db = Mock()
    mock_db.query().filter().first.side_effect = [None, Mock()]
    user = make_user_create()
    with pytest.raises(HTTPException) as exc:
        register_user(user, mock_db)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Email already exists."

@pytest.mark.asyncio
async def test_get_openlibrary_cache_info(monkeypatch):
    CacheInfo = namedtuple("CacheInfo", ["hits", "misses", "maxsize", "currsize"])
    monkeypatch.setattr(
        "app.main.cached_search_openlibrary.cache_info",
        lambda: CacheInfo(hits=1, misses=2, maxsize=10, currsize=3)
    )
    result = await get_openlibrary_cache_info()
    assert result == {"hits": 1, "misses": 2, "maxsize": 10, "currsize": 3}

@pytest.mark.asyncio
async def test_clear_openlibrary_cache(monkeypatch):
    called = {}
    async def fake_clear():
        called["ok"] = True
    monkeypatch.setattr("app.main.cached_search_openlibrary.cache_clear", fake_clear)
    result = await clear_openlibrary_cache()
    assert result == {"detail": "Cache cleared."}
    assert called["ok"]