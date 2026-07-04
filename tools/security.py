"""
CompeteIQ - Security Utilities
Implements input validation, URL sanitization, and rate limiting.
Demonstrates Security Features (Competition Concept #4).
"""

import re
import time
from urllib.parse import urlparse
from typing import Tuple

from config.settings import (
    MAX_URL_LENGTH,
    ALLOWED_SCHEMES,
    BLOCKED_DOMAINS,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
)


# --- Rate Limiter ---
class RateLimiter:
    """Simple in-memory rate limiter to prevent abuse."""

    def __init__(self, max_requests: int = RATE_LIMIT_MAX_REQUESTS,
                 window_seconds: int = RATE_LIMIT_WINDOW_SECONDS):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: list[float] = []

    def is_allowed(self) -> Tuple[bool, str]:
        """Check if a new request is allowed within the rate limit."""
        now = time.time()
        # Remove expired timestamps
        self.requests = [t for t in self.requests if now - t < self.window_seconds]

        if len(self.requests) >= self.max_requests:
            wait_time = int(self.window_seconds - (now - self.requests[0]))
            return False, f"Rate limit exceeded. Please wait {wait_time}s before next analysis."

        self.requests.append(now)
        return True, "OK"


# Singleton rate limiter instance
rate_limiter = RateLimiter()


# --- URL Validation ---
def validate_url(url: str) -> Tuple[bool, str]:
    """
    Validate and sanitize a URL input.
    Prevents SSRF attacks, injection, and malformed inputs.

    Returns:
        (is_valid, message) tuple
    """
    # Strip whitespace
    url = url.strip()

    # Check empty
    if not url:
        return False, "URL cannot be empty."

    # Check length (prevent buffer overflow attempts)
    if len(url) > MAX_URL_LENGTH:
        return False, f"URL exceeds maximum length of {MAX_URL_LENGTH} characters."

    # Check for script injection attempts
    dangerous_patterns = [
        r"<script", r"javascript:", r"data:", r"vbscript:",
        r"on\w+\s*=", r"eval\(", r"exec\(",
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return False, "URL contains potentially malicious content."

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format."

    # Validate scheme
    if parsed.scheme not in ALLOWED_SCHEMES:
        return False, f"Only {', '.join(ALLOWED_SCHEMES)} URLs are allowed."

    # Validate hostname exists
    if not parsed.hostname:
        return False, "URL must contain a valid hostname."

    # Block internal/private domains (SSRF prevention)
    hostname = parsed.hostname.lower()
    for blocked in BLOCKED_DOMAINS:
        if blocked in hostname:
            return False, "Internal/private URLs are not allowed."

    # Block IP addresses (additional SSRF prevention)
    ip_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    if re.match(ip_pattern, hostname):
        return False, "Direct IP addresses are not allowed. Please use a domain name."

    # Validate it looks like a real website
    if "." not in hostname:
        return False, "Please enter a valid website URL (e.g., https://www.example.com)."

    return True, url


def sanitize_output(text: str) -> str:
    """
    Sanitize agent output to prevent XSS and data leakage.
    Removes any potential PII or sensitive data patterns from output.
    """
    # Remove potential API keys or tokens
    text = re.sub(r"[A-Za-z0-9_-]{20,}(?:key|token|secret|api)[A-Za-z0-9_-]*",
                  "[REDACTED]", text, flags=re.IGNORECASE)

    # Remove email patterns (PII protection)
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                  "[EMAIL REDACTED]", text)

    return text
