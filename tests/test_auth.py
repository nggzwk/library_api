import pytest
from app.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_user,
    authenticate_user,
    get_current_user,
)

def test_password_hash_and_verify():
    password = "test123"
    hashed = get_password_hash(password)

    assert verify_password(password, hashed)
    assert not verify_password("wrongpass", hashed)

def test_create_access_token():
    data = {"sub": "testuser"}
    token = create_access_token(data)

    assert isinstance(token, str)

def test_get_user(mocker):
    mock_db = mocker.Mock()
    mock_user = mocker.Mock()
    mock_user.username = "test123"
    mock_db.query().filter().first.return_value = mock_user

    user = get_user(mock_db, "test123")
    assert user.username == "test123"

    mock_db.query().filter().first.return_value = None
    user_none = get_user(mock_db, "nouser")
    assert user_none is None

def test_authenticate_user(mocker):
    mock_db = mocker.Mock()
    mock_user = mocker.Mock()
    mock_user.username = "test123"
    mock_user.hashed_password = get_password_hash("password123")
    mock_db.query().filter().first.return_value = mock_user

    # Correct password
    user = authenticate_user(mock_db, "test123", "password123")
    assert user == mock_user

    # Wrong password
    user_invalid = authenticate_user(mock_db, "test123", "wrongpass")
    assert user_invalid is False

    # User dont exist
    mock_db.query().filter().first.return_value = None
    user_none = authenticate_user(mock_db, "nouser", "password123")
    assert user_none is False

def test_get_current_user(mocker):
    mock_db = mocker.Mock()
    mock_user = mocker.Mock()
    mock_user.username = "test123"
    mock_db.query().filter().first.return_value = mock_user

    # Create token with 'sub' claim
    token = create_access_token({"sub": "test123"})
    # Patch Depends to pass token and db
    user = get_current_user(token=token, db=mock_db)
    assert user == mock_user

    # Invalid token
    with pytest.raises(Exception):
        get_current_user(token="invalid.token", db=mock_db)

    # Token with missing 'sub'
    bad_token = create_access_token({})
    with pytest.raises(Exception):
        get_current_user(token=bad_token, db=mock_db)

    # User not found
    mock_db.query().filter().first.return_value = None
    token = create_access_token({"sub": "nouser"})
    with pytest.raises(Exception):
        get_current_user(token=token, db=mock_db)