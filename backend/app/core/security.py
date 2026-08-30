from __future__ import annotations

import hashlib
import hmac
import secrets


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_invite_code(candidate: str, allowed_codes: tuple[str, ...]) -> str | None:
    candidate_hash = secret_hash(candidate)
    matched_hash: str | None = None
    for configured in allowed_codes:
        configured_hash = secret_hash(configured)
        if hmac.compare_digest(candidate_hash, configured_hash):
            matched_hash = configured_hash
    return matched_hash


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_token_hash(token: str, session_secret: str) -> str:
    return hmac.new(
        session_secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def new_preview_token() -> str:
    return secrets.token_urlsafe(24)
