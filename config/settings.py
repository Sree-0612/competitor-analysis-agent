"""
CompeteIQ - AI-Powered Competitor Analysis Agent
Configuration and settings management.

Loads API keys securely from environment variables or Streamlit secrets.
Never hardcodes credentials.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """Retrieve secret from Streamlit secrets (cloud) or env vars (local)."""
    try:
        import streamlit as st
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


# --- API Keys (loaded securely) ---
GOOGLE_API_KEY = _get_secret("GOOGLE_API_KEY")
TAVILY_API_KEY = _get_secret("TAVILY_API_KEY")

# --- Agent Configuration ---
MODEL_NAME = "gemini-2.5-flash"
MAX_COMPETITORS = 4
MAX_SEARCH_RESULTS = 10
REQUEST_TIMEOUT = 30

# --- Security Configuration ---
MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = ["http", "https"]
BLOCKED_DOMAINS = [
    "localhost", "127.0.0.1", "0.0.0.0", "10.", "172.16.",
    "192.168.", "internal", "intranet", "corp"
]
RATE_LIMIT_MAX_REQUESTS = 5  # Max analyses per session
RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minute window

# --- Analysis Configuration ---
COMPARISON_DIMENSIONS = [
    "product_features",
    "pricing_strategy",
    "market_positioning",
    "technology_innovation",
    "customer_experience",
    "brand_perception",
    "sustainability",
    "digital_presence",
]

# --- Application Metadata ---
APP_NAME = "CompeteIQ"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "AI-Powered Competitor Analysis Agent"
