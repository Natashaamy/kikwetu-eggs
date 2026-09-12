"""Shared Flask extensions initialized by the application factory."""

from hashlib import sha256
from ipaddress import ip_address

from flask import current_app, request
from flask_limiter import Limiter


def _validated_ip(value):
    """Return a normalized IP address, or None when the value is invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(ip_address(value.strip()))
    except ValueError:
        return None


def get_client_ip():
    """Resolve the limiter key without trusting forwarded headers locally."""
    remote_address = _validated_ip(request.remote_addr) or "unknown"
    if not current_app.config.get("TRUST_PROXY_HEADERS", False):
        return remote_address

    # Render documents the first X-Forwarded-For entry as the real client.
    forwarded_for = request.headers.get("X-Forwarded-For")
    if not forwarded_for:
        return remote_address
    forwarded_client = _validated_ip(forwarded_for.split(",", 1)[0])
    return forwarded_client or remote_address


def get_login_identifier_key():
    """Return a fixed-length key for the submitted, normalized login name."""
    data = request.get_json(silent=True)
    submitted_identifier = data.get("username") if isinstance(data, dict) else None
    if submitted_identifier is None:
        normalized_identifier = "<missing>"
    else:
        normalized_identifier = " ".join(
            str(submitted_identifier).strip().split()
        ).casefold()
        if not normalized_identifier:
            normalized_identifier = "<missing>"

    digest = sha256(normalized_identifier.encode("utf-8")).hexdigest()
    return f"login-id:{digest}"


limiter = Limiter(
    key_func=get_client_ip,
    default_limits=[],
    storage_uri="memory://",
    headers_enabled=True,
)
