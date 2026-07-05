"""
Rate limiting - keyed by JWT subject (user id) when the request is authenticated,
falling back to client IP for unauthenticated endpoints (register/login), so one
abusive account can't be worked around by rotating IPs and vice versa.

Trade-off worth noting: this uses slowapi's default in-memory store, which is
per-process. That's correct for the single-instance deployment in this project's
docker-compose.yml. Running multiple API replicas behind a load balancer would
need a shared store (slowapi supports Redis) so limits are enforced globally
rather than per-replica.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.security import decode_access_token


def rate_limit_key(request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        user_id = decode_access_token(token)
        if user_id:
            return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=rate_limit_key)
