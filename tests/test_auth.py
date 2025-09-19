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