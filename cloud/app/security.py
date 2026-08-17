import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings

AGENT_KEY_PREFIX = "ioniq5_ak_"
ENROLLMENT_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no look-alike characters


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: str, org_id: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "org": org_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


def generate_agent_key() -> str:
    return AGENT_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_agent_key(key: str) -> str:
    """Peppered SHA-256.

    Deliberately not bcrypt: these are server-generated 256-bit tokens, not
    user-chosen passwords, so they aren't guessable and don't need a slow hash -
    and unlike a password, one is verified on every ingest request, by hash
    lookup rather than by comparing against each stored row.
    """
    return hmac.new(  # codeql[py/weak-sensitive-data-hashing]
        get_settings().api_key_pepper.encode(), key.encode(), hashlib.sha256
    ).hexdigest()


def generate_enrollment_code() -> str:
    raw = "".join(secrets.choice(ENROLLMENT_CODE_ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def hash_enrollment_code(code: str) -> str:
    return hash_agent_key(code.strip().upper())
