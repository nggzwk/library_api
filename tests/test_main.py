import pytest
from unittest.mock import patch, Mock
from fastapi import HTTPException

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