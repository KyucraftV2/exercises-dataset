import hashlib
import hmac
import re
import secrets

PBKDF2_ITERATIONS = 600_000
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256


def validate_username(username: str) -> bool:
    return bool(USERNAME_RE.match(username))


def validate_password(password: str) -> bool:
    return MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"{PBKDF2_ITERATIONS}${salt}${digest.hex()}"


# Used to equalize login() timing between "user doesn't exist" and "wrong
# password" - see storage.login. Fixed, not secret: verify_password always
# fails against it since no real password produces this exact hash.
DUMMY_HASH = f"{PBKDF2_ITERATIONS}${'0' * 32}${'0' * 64}"


def verify_password(password: str, stored: str) -> bool:
    try:
        iterations_str, salt, expected_hex = stored.split("$")
        iterations = int(iterations_str)
        salt_bytes = bytes.fromhex(salt)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
    return hmac.compare_digest(digest.hex(), expected_hex)


def generate_token() -> str:
    return secrets.token_urlsafe(32)
