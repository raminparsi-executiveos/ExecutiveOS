import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)
failed_logins: dict[str, deque[float]] = defaultdict(deque)
login_lock = threading.Lock()
LOGIN_WINDOW_SECONDS = 15 * 60
MAX_LOGIN_ATTEMPTS = 5
TOKEN_LIFETIME_SECONDS = 12 * 60 * 60


def auth_required() -> bool:
    return bool(os.getenv("EXECUTIVEOS_PASSWORD")) or os.getenv("RENDER") == "true"


def auth_configured() -> bool:
    password = os.getenv("EXECUTIVEOS_PASSWORD", "")
    secret = os.getenv("SESSION_SECRET", "")
    return len(password) >= 12 and len(secret) >= 32


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret() -> bytes:
    secret = os.getenv("SESSION_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    return secret.encode()


def issue_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS,
        "nonce": secrets.token_urlsafe(12),
    }
    encoded_payload = _encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _encode(hmac.new(_secret(), encoded_payload.encode(), hashlib.sha256).digest())
    return f"{encoded_payload}.{signature}"


def validate_token(token: str) -> str:
    try:
        encoded_payload, supplied_signature = token.split(".", 1)
        expected_signature = _encode(hmac.new(_secret(), encoded_payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("signature")
        payload = json.loads(_decode(encoded_payload))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")
        return str(payload["sub"])
    except (binascii.Error, KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
    if not auth_required():
        return "local-development"
    if not auth_configured():
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return validate_token(credentials.credentials)


def authenticate(request: Request, username: str, password: str) -> str:
    if not auth_configured():
        raise HTTPException(status_code=503, detail="Authentication is not configured")

    client_key = request.client.host if request.client else "unknown"
    now = time.time()
    with login_lock:
        attempts = failed_logins[client_key]
        while attempts and attempts[0] < now - LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= MAX_LOGIN_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later.")

    expected_username = os.getenv("EXECUTIVEOS_USERNAME", "admin")
    expected_password = os.getenv("EXECUTIVEOS_PASSWORD", "")
    valid = hmac.compare_digest(username, expected_username) & hmac.compare_digest(password, expected_password)
    if not valid:
        with login_lock:
            failed_logins[client_key].append(now)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    with login_lock:
        failed_logins.pop(client_key, None)
    return issue_token(expected_username)
