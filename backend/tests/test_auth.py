from backend import auth


def test_validate_username_accepts_valid_forms():
    assert auth.validate_username("abc")
    assert auth.validate_username("a" * 32)
    assert auth.validate_username("under_score-hyphen123")


def test_validate_username_rejects_invalid_forms():
    assert not auth.validate_username("ab")  # too short
    assert not auth.validate_username("a" * 33)  # too long
    assert not auth.validate_username("has space")
    assert not auth.validate_username("has@symbol")
    assert not auth.validate_username("")


def test_validate_password_length_bounds():
    assert not auth.validate_password("short")
    assert auth.validate_password("exactly8")
    assert auth.validate_password("x" * auth.MAX_PASSWORD_LENGTH)
    assert not auth.validate_password("x" * (auth.MAX_PASSWORD_LENGTH + 1))


def test_hash_password_roundtrip_verifies():
    hashed = auth.hash_password("correct horse battery staple")
    assert auth.verify_password("correct horse battery staple", hashed)


def test_hash_password_rejects_wrong_password():
    hashed = auth.hash_password("correct horse battery staple")
    assert not auth.verify_password("wrong password", hashed)


def test_hash_password_uses_a_fresh_salt_each_time():
    a = auth.hash_password("same password")
    b = auth.hash_password("same password")
    assert a != b  # different salts -> different stored hashes
    assert auth.verify_password("same password", a)
    assert auth.verify_password("same password", b)


def test_verify_password_rejects_malformed_stored_hash():
    assert not auth.verify_password("anything", "not-the-right-format")


def test_dummy_hash_never_verifies():
    # used to equalize login() timing for a nonexistent user - must never
    # accidentally match a real password
    assert not auth.verify_password("", auth.DUMMY_HASH)
    assert not auth.verify_password("password", auth.DUMMY_HASH)


def test_generate_token_is_unique_and_url_safe():
    tokens = {auth.generate_token() for _ in range(50)}
    assert len(tokens) == 50
    for token in tokens:
        assert all(c.isalnum() or c in "-_" for c in token)
