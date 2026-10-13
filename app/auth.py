import hashlib
import hmac
import secrets
import time
from typing import Dict, Optional, Set, Tuple
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings

# In-memory session token store: token -> expires_at_timestamp
_active_sessions: Dict[str, float] = {}
_revoked_tokens: Set[str] = set()

http_bearer_scheme = HTTPBearer(auto_error=False)

def _sign_payload(payload_hex: str, pin: str) -> str:
    """Computes a 32-hex-char (128-bit) HMAC-SHA256 signature over payload_hex."""
    key = (pin.strip() or "7777").encode("utf-8")
    return hmac.new(key, payload_hex.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

def verify_pin(candidate_pin: str) -> bool:
    """
    Validates candidate PIN using constant-time string comparison.
    """
    if not candidate_pin:
        return False
    current_pin = get_settings().pin
    return secrets.compare_digest(candidate_pin.strip(), current_pin.strip())

def create_session_token() -> Tuple[str, int]:
    """
    Generates a cryptographically secure 64-char hex token (32 bytes):
    - 16 hex chars: 64-bit random nonce
    - 16 hex chars: 64-bit expiration timestamp
    - 32 hex chars: 128-bit HMAC-SHA256 signature keyed with current PIN
    Works both stateful (in-memory) and stateless (serverless cold starts).
    Returns (token_str, expires_in_seconds).
    """
    nonce_hex = secrets.token_hex(8)
    expires_in = get_settings().token_expire_seconds
    expires_at = int(time.time() + expires_in)
    exp_hex = f"{expires_at:016x}"
    payload_hex = f"{nonce_hex}{exp_hex}"
    sig_hex = _sign_payload(payload_hex, get_settings().pin)
    token = f"{payload_hex}{sig_hex}"
    _active_sessions[token] = float(expires_at)
    _revoked_tokens.discard(token)
    return token, expires_in

def is_valid_token(token: Optional[str]) -> bool:
    """
    Validates whether a token is active and has not expired.
    Supports both stateful in-memory lookup and stateless HMAC verification
    for 24/7 serverless cloud deployments.
    """
    if not token or not isinstance(token, str):
        return False

    if token in _revoked_tokens:
        return False

    now = time.time()
    expires_at = _active_sessions.get(token)
    if expires_at is not None:
        if now > expires_at:
            _active_sessions.pop(token, None)
            return False
        return True

    # Stateless HMAC verification for serverless cold starts (64-char hex token)
    if len(token) == 64:
        try:
            payload_hex = token[:32]
            exp_ts = int(token[16:32], 16)
            sig_candidate = token[32:]
            expected_sig = _sign_payload(payload_hex, get_settings().pin)
            if secrets.compare_digest(sig_candidate.lower(), expected_sig.lower()):
                if now <= exp_ts:
                    _active_sessions[token] = float(exp_ts)
                    return True
        except ValueError:
            return False

    return False

def revoke_token(token: str) -> None:
    """Removes token from active sessions and marks it revoked."""
    _active_sessions.pop(token, None)
    _revoked_tokens.add(token)

def clear_all_sessions() -> None:
    """Clears all sessions (useful for tests)."""
    _active_sessions.clear()
    _revoked_tokens.clear()

async def require_auth(
    request: Request,
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer_scheme)
) -> str:
    """
    FastAPI security dependency protecting endpoints.
    Accepts:
    1. Authorization: Bearer <token> header
    2. session_token cookie
    Raises HTTP 401 Unauthorized for missing or invalid tokens.
    """
    token: Optional[str] = None

    # 1. Check Bearer credentials from Authorization header
    if bearer_creds and bearer_creds.credentials:
        token = bearer_creds.credentials.strip()
    
    # 2. Fallback to raw Authorization header if not parsed by scheme
    if not token:
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
        if auth_header:
            parts = auth_header.strip().split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
            elif len(parts) == 1:
                token = parts[0]

    # 3. Fallback to Cookie
    if not token:
        token = request.cookies.get("session_token") or request.cookies.get("gg_hud_token")

    # Validate
    if not token or not is_valid_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return token
