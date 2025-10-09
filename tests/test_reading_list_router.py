import pytest
from unittest.mock import MagicMock, Mock, patch
from fastapi import HTTPException
from app.routers.reading_list_router import (
    dont_allow_empty_user,
    create_reading_list,
    get_reading_lists,
    delete_reading_list
)

@pytest.fixture
def mock_db():
    return Mock()

@pytest.fixture
def mock_user():
    user = Mock()
    user.id = 1
    user.username = "anna"
    return user

@pytest.fixture
def mock_current_user():
    return Mock()

class DummyForm:
    def __init__(self, username):
        self.username = username

def test_dont_allow_empty_user_valid():
    assert dont_allow_empty_user("anna") is None

def test_dont_allow_empty_user_empty():
    with pytest.raises(HTTPException):
        dont_allow_empty_user("")

def test_dont_allow_empty_user_whitespace():
    with pytest.raises(HTTPException):
        dont_allow_empty_user("   ")

def test_create_reading_list_user_not_found(mock_db, mock_current_user):
    mock_db.query().filter().first.return_value = None
    with pytest.raises(HTTPException) as exc:
        create_reading_list(
            username="ghost",
            name="My List",
            db=mock_db,
            current_user=mock_current_user
        )
    assert exc.value.status_code == 404
    assert "User not found" in exc.value.detail

def test_create_reading_list_max_limit(mock_db, mock_user, mock_current_user):
    mock_db.query().filter().first.return_value = mock_user
    mock_db.query().filter().count.return_value = 3
    with pytest.raises(HTTPException) as exc:
        create_reading_list(
            username="anna",
            name="New List",
            db=mock_db,
            current_user=mock_current_user
        )
    assert exc.value.status_code == 400
    assert "3 reading lists" in exc.value.detail

def test_create_reading_list_duplicate_name(mock_db, mock_user, mock_current_user):
    mock_db.query().filter().first.return_value = mock_user
    mock_db.query().filter().count.return_value = 1
    mock_db.query().filter().filter().first.return_value = Mock()
    with pytest.raises(HTTPException) as exc:
        create_reading_list(
            username="anna",
            name="Existing List",
            db=mock_db,
            current_user=mock_current_user
        )
    assert exc.value.status_code == 400
    assert "already exists" in exc.value.detail

@patch("app.routers.reading_list_router.models.ReadingList")
def test_create_reading_list_success(mock_reading_list_model, mock_db, mock_user, mock_current_user):
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    mock_db.query.return_value.filter.return_value.count.return_value = 1
    
    duplicate_check_mock = Mock()
    duplicate_check_mock.filter.return_value.first.return_value = None
    
    mock_db.query.side_effect = [
        mock_db.query.return_value,
        mock_db.query.return_value,
        duplicate_check_mock
    ]
    
    reading_list_obj = Mock(id=42, list_name="My List", user_id=1)
    mock_reading_list_model.return_value = reading_list_obj
    
    result = create_reading_list(
        username="anna",
        name="My List",
        db=mock_db,
        current_user=mock_current_user
    )
    
    assert result.id == 42

def test_get_reading_lists_user_not_found(mock_db, mock_current_user):
    mock_db.query().filter().first.return_value = None
    with pytest.raises(HTTPException) as exc:
        get_reading_lists(
            username="user",
            db=mock_db,
            current_user=mock_current_user
        )
    assert exc.value.status_code == 404
    assert "User not found" in exc.value.detail

def test_get_reading_lists_empty_username(mock_db, mock_current_user):
    with pytest.raises(HTTPException) as exc:
        get_reading_lists(
            username="",
            db=mock_db,
            current_user=mock_current_user
        )
    assert exc.value.status_code == 400
    assert "non-empty username" in exc.value.detail

def test_get_reading_lists_success_no_lists(mock_db, mock_user, mock_current_user):
    mock_db.query().filter().first.return_value = mock_user
    mock_db.query().filter().all.return_value = []
    
    result = get_reading_lists(
        username="anna",
        db=mock_db,
        current_user=mock_current_user
    )
    
    assert result == []

def test_get_reading_lists_success_with_lists(mock_db, mock_user, mock_current_user):
    mock_db.query().filter().first.return_value = mock_user
    
    mock_book = Mock()
    mock_book.id = 1
    mock_book.title = "Test Book"
    mock_book.author = "Test Author"
    
    mock_reading_list = Mock()
    mock_reading_list.id = 42
    mock_reading_list.list_name = "My List"
    mock_reading_list.books = [mock_book]
    
    mock_db.query().filter().all.return_value = [mock_reading_list]
    
    result = get_reading_lists(
        username="anna",
        db=mock_db,
        current_user=mock_current_user
    )
    
    assert len(result) == 1
    assert result[0].id == 42
    assert result[0].username == "anna"
    assert result[0].reading_list_name == "My List"
    assert len(result[0].books) == 1
    assert result[0].books[0].title == "Test Book"

def test_delete_reading_list_empty_username(mock_db, mock_current_user):
    with pytest.raises(HTTPException) as exc:
        delete_reading_list(
            username="",
            name="My List",
            db=mock_db,
            current_user=mock_current_user
        )
    assert exc.value.status_code == 400
    assert "non-empty username" in exc.value.detail

def test_delete_reading_list_empty_name(mock_db, mock_current_user):
    with pytest.raises(HTTPException) as exc:
        delete_reading_list(
            username="anna",
            name="",
            db=mock_db,
            current_user=mock_current_user
        )
    assert exc.value.status_code == 400
    assert "non-empty reading list name" in exc.value.detail

def test_delete_reading_list_user_not_found(mock_db, mock_current_user):
    mock_db.query().filter().first.return_value = None
    with pytest.raises(HTTPException) as exc:
        delete_reading_list(
            username="ghost",
            name="My List",
            db=mock_db,
            current_user=mock_current_user
        )
    assert exc.value.status_code == 404
    assert "User not found" in exc.value.detail

def test_delete_reading_list_not_found(mock_db, mock_user, mock_current_user):
    user_query_mock = Mock()
    user_query_mock.filter.return_value.first.return_value = mock_user
    
    reading_list_query_mock = Mock()
    reading_list_query_mock.filter.return_value.first.return_value = None
    
    mock_db.query.side_effect = [user_query_mock, reading_list_query_mock]
    
    with pytest.raises(HTTPException) as exc:
        delete_reading_list(
            username="anna",
            name="Non-existent List",
            db=mock_db,
            current_user=mock_current_user
        )
    assert exc.value.status_code == 404
    assert "Reading list not found" in exc.value.detail

def test_delete_reading_list_success_no_books(mock_db, mock_user, mock_current_user):
    user_query_mock = Mock()
    user_query_mock.filter.return_value.first.return_value = mock_user
    
    mock_reading_list = Mock()
    mock_reading_list.id = 42
    mock_reading_list.list_name = "My List"
    mock_reading_list.books = []
    
    reading_list_query_mock = Mock()
    reading_list_query_mock.filter.return_value.first.return_value = mock_reading_list
    
    mock_db.query.side_effect = [user_query_mock, reading_list_query_mock]
    
    mock_db.delete = Mock()
    mock_db.commit = Mock()
    
    result = delete_reading_list(
        username="anna",
        name="My List",
        db=mock_db,
        current_user=mock_current_user
    )
    
    assert result.id == 42
    assert result.username == "anna"
    assert result.reading_list_name == "My List"
    assert result.books == []
    mock_db.delete.assert_called_once_with(mock_reading_list)
    mock_db.commit.assert_called_once()

def test_delete_reading_list_success_with_books(mock_db, mock_user, mock_current_user):
    user_query_mock = Mock()
    user_query_mock.filter.return_value.first.return_value = mock_user
    
    mock_book = Mock()
    mock_book.id = 1
    mock_book.title = "Test Book"
    mock_book.author = "Test Author"
    
    mock_reading_list = Mock()
    mock_reading_list.id = 42
    mock_reading_list.list_name = "My List"
    mock_reading_list.books = [mock_book]
    
    reading_list_query_mock = Mock()
    reading_list_query_mock.filter.return_value.first.return_value = mock_reading_list
    
    mock_db.query.side_effect = [user_query_mock, reading_list_query_mock]
    
    mock_db.delete = Mock()
    mock_db.commit = Mock()
    
    result = delete_reading_list(
        username="anna",
        name="My List",
        db=mock_db,
        current_user=mock_current_user
    )
    
    assert result.id == 42
    assert result.username == "anna"
    assert result.reading_list_name == "My List"
    assert len(result.books) == 1
    assert result.books[0].title == "Test Book"
    mock_db.delete.assert_called_once_with(mock_reading_list)
    mock_db.commit.assert_called_once()

def test_delete_reading_list_database_error(mock_db, mock_user, mock_current_user):
    user_query_mock = Mock()
    user_query_mock.filter.return_value.first.return_value = mock_user
    
    mock_reading_list = Mock()
    mock_reading_list.id = 42
    mock_reading_list.list_name = "My List"
    mock_reading_list.books = []
    
    reading_list_query_mock = Mock()
    reading_list_query_mock.filter.return_value.first.return_value = mock_reading_list
    
    mock_db.query.side_effect = [user_query_mock, reading_list_query_mock]
    
    mock_db.delete = Mock()
    mock_db.commit = Mock(side_effect=Exception("Database error"))
    mock_db.rollback = Mock()
    
    with pytest.raises(HTTPException) as exc:
        delete_reading_list(
            username="anna",
            name="My List",
            db=mock_db,
            current_user=mock_current_user
        )
    assert exc.value.status_code == 500
    assert "Database error" in exc.value.detail
    mock_db.rollback.assert_called_once()