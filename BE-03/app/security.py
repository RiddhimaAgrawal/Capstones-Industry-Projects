"""API-key generation/hashing, password hashing and login tokens."""
import hashlib
import hmac
import os
import secrets
import time

import jwt

from .config import settings

KEY_PREFIX = "apk_"


def generate_api_key() -> tuple[str, str, str]:
    """Return (plaintext, display_prefix, hash). Plaintext is shown ONCE."""
    plaintext = KEY_PREFIX + secrets.token_urlsafe(32)
    return plaintext, plaintext[:12], hash_api_key(plaintext)


def hash_api_key(plaintext: str) -> str:
    # Keys are 256-bit random so a fast keyed hash is safe (no need for bcrypt),
    # and it keeps per-request lookup cheap. The pepper protects against a DB-only leak.
    return hmac.new(settings.KEY_PEPPER.encode(), plaintext.encode(), hashlib.sha256).hexdigest()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(dk.hex(), dk_hex)


def create_token(customer_id: int) -> str:
    now = int(time.time())
    return jwt.encode({"sub": str(customer_id), "iat": now, "exp": now + settings.JWT_TTL_SECONDS},
                      settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> int | None:
    try:
        return int(jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])["sub"])
    except Exception:
        return None
