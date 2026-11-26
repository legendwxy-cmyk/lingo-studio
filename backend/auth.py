from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections import defaultdict
from typing import Any

from fastapi import HTTPException, Request, Response

COOKIE_NAME = "lingoreel_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
RATE_WINDOW_SEC = 300
MAX_FAILURES_PER_WINDOW = 10

_FAILED_ATTEMPTS: dict[str, list[float]] = defaultdict(list)


def get_configured_password() -> str:
    return os.getenv("APP_ACCESS_PASSWORD", "").strip()


def is_auth_enabled() -> bool:
    return bool(get_configured_password())


def _get_signing_key() -> bytes:
    secret = os.getenv("APP_SECRET_KEY", "").strip()
    if secret:
        return secret.encode("utf-8")
    pwd = get_configured_password()
    return hashlib.sha256(f"lingoreel-signing-v1:{pwd}".encode("utf-8")).digest()


def _password_fingerprint() -> str:
    pwd = get_configured_password()
    return hashlib.sha256(f"lingoreel-pwd-v1:{pwd}".encode("utf-8")).hexdigest()[:16]


def issue_session_token() -> str:
    exp = int(time.time()) + SESSION_MAX_AGE
    payload = f"v1:{_password_fingerprint()}:{exp}"
    sig = hmac.new(_get_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_session_token(token: str | None) -> bool:
    if not is_auth_enabled():
        return True
    if not token:
        return False
    parts = token.split(":")
    if len(parts) != 4:
        return False
    ver, fp, exp_str, sig = parts
    if ver != "v1":
        return False
    if not hmac.compare_digest(fp, _password_fingerprint()):
        return False
    try:
        exp = int(exp_str)
    except ValueError:
        return False
    if exp < int(time.time()):
        return False
    payload = f"{ver}:{fp}:{exp_str}"
    expected_sig = hmac.new(_get_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected_sig)


def is_request_authenticated(request: Request) -> bool:
    if not is_auth_enabled():
        return True
    token = request.cookies.get(COOKIE_NAME)
    return verify_session_token(token)


def _client_ip(request: Request) -> str:
    trust_proxy = os.getenv("TRUST_PROXY", "").strip().lower() in {"1", "true", "yes"}
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def check_and_verify_login(request: Request, password: str) -> None:
    if not is_auth_enabled():
        return
    ip = _client_ip(request)
    now = time.time()
    recent = [ts for ts in _FAILED_ATTEMPTS[ip] if now - ts < RATE_WINDOW_SEC]
    _FAILED_ATTEMPTS[ip] = recent
    if len(recent) >= MAX_FAILURES_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail="密码错误次数过多，请 5 分钟后再试。",
        )

    expected = get_configured_password()
    if not hmac.compare_digest(password.strip(), expected):
        _FAILED_ATTEMPTS[ip].append(now)
        remaining = max(0, MAX_FAILURES_PER_WINDOW - len(_FAILED_ATTEMPTS[ip]))
        raise HTTPException(
            status_code=401,
            detail=f"访问口令不正确（剩余 {remaining} 次尝试机会）。",
        )
    _FAILED_ATTEMPTS.pop(ip, None)


def set_session_cookie(request: Request, response: Response) -> None:
    is_https = (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=issue_session_token(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=is_https,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def auth_status_payload(request: Request) -> dict[str, Any]:
    enabled = is_auth_enabled()
    return {
        "auth_enabled": enabled,
        "authenticated": True if not enabled else is_request_authenticated(request),
    }
