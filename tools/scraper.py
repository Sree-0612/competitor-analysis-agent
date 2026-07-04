"""
CompeteIQ - Web Intelligence Tool
Extracts structured information from company websites.

Two-tier strategy:
  1. Jina Reader (https://r.jina.ai) - converts JS-heavy sites to clean Markdown,
     bypassing anti-bot measures that stop 90% of basic scrapers. Free, no API key.
  2. httpx + BeautifulSoup fallback - if Jina is unavailable.

LLMs perform significantly better on clean Markdown than raw HTML.
"""

import httpx
from bs4 import BeautifulSoup
from typing import Optional

from config.settings import REQUEST_TIMEOUT


JINA_READER_ENDPOINT = "https://r.jina.ai/"


def scrape_website(url: str) -> dict:
    """
    Extract business intelligence from a website.

    Strategy: try Jina Reader first (clean Markdown, handles JavaScript &
    anti-bot), then fall back to direct httpx + BeautifulSoup scraping.

    Args:
        url: The website URL to analyze

    Returns:
        Dictionary with extracted content or error details.
        Includes 'method' key indicating which engine succeeded.
    """
    # --- Tier 1: Jina Reader (JS rendering + anti-bot bypass) ---
    jina_result = _scrape_with_jina(url)
    if jina_result.get("success"):
        return jina_result

    # --- Tier 2: Direct httpx + BeautifulSoup fallback ---
    return _scrape_with_httpx(url)


def _scrape_with_jina(url: str) -> dict:
    """
    Fetch a URL via Jina Reader, returning clean Markdown.

    Jina renders JavaScript and bypasses common anti-bot measures,
    then returns LLM-optimized Markdown. Free tier, no API key required.
    """
    try:
        headers = {
            "Accept": "text/markdown",
            "X-Return-Format": "markdown",
            "User-Agent": "CompeteIQ/1.0 (+https://competeiq.streamlit.app)",
        }
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            response = client.get(f"{JINA_READER_ENDPOINT}{url}", headers=headers)
            response.raise_for_status()

        markdown = response.text or ""
        if len(markdown.strip()) < 50:
            return {"success": False, "error": "Jina returned insufficient content."}

        title, meta_description, headings = _parse_markdown_structure(markdown)

        return {
            "success": True,
            "method": "jina-reader",
            "url": url,
            "title": title,
            "meta_description": meta_description,
            "headings": headings[:20],
            "main_content": markdown[:5000],  # Markdown is denser than HTML text
            "key_links": _extract_markdown_links(markdown)[:15],
        }
    except Exception as e:
        return {"success": False, "error": f"Jina Reader unavailable: {str(e)[:100]}"}


def _parse_markdown_structure(markdown: str) -> tuple[str, str, list[str]]:
    """Extract title, description, and headings from Markdown."""
    lines = markdown.split("\n")
    title = "Unknown"
    meta_description = ""
    headings: list[str] = []

    # Jina prepends 'Title:' and 'URL Source:' metadata lines
    for line in lines[:8]:
        if line.startswith("Title:"):
            title = line.replace("Title:", "").strip()
        elif line.startswith("Markdown Content:"):
            break

    for line in lines:
        stripped = line.strip()
        # Markdown headings (#, ##, ###)
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip()
            if 3 < len(heading_text) < 200:
                headings.append(heading_text)
        # First substantial paragraph as description
        elif not meta_description and len(stripped) > 60 and not stripped.startswith(("#", "-", "*", "|", "!", "[")):
            meta_description = stripped[:300]

    if title == "Unknown" and headings:
        title = headings[0]

    return title, meta_description, headings


def _extract_markdown_links(markdown: str) -> list[str]:
    """Extract anchor text from Markdown links [text](url)."""
    import re
    links = []
    seen = set()
    for match in re.finditer(r"\[([^\]]+)\]\([^)]+\)", markdown):
        text = match.group(1).strip()
        if 2 < len(text) < 50 and text.lower() not in seen and not text.startswith("!"):
            seen.add(text.lower())
            links.append(text)
    return links


def _scrape_with_httpx(url: str) -> dict:
    """Direct HTML scraping fallback using httpx + BeautifulSoup."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            max_redirects=10,
        ) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Extract structured data
        title = _extract_title(soup)
        meta_description = _extract_meta_description(soup)
        headings = _extract_headings(soup)
        main_content = _extract_main_content(soup)
        links = _extract_nav_links(soup, url)

        return {
            "success": True,
            "method": "httpx-beautifulsoup",
            "url": url,
            "title": title,
            "meta_description": meta_description,
            "headings": headings[:20],  # Top 20 headings
            "main_content": main_content[:3000],  # First 3000 chars
            "key_links": links[:15],  # Top 15 navigation links
        }

    except httpx.TimeoutException:
        return {"success": False, "url": url, "error": "Website took too long to respond."}
    except httpx.HTTPStatusError as e:
        return {"success": False, "url": url, "error": f"HTTP error {e.response.status_code}"}
    except Exception as e:
        return {"success": False, "url": url, "error": f"Could not access website: {str(e)[:100]}"}


def _extract_title(soup: BeautifulSoup) -> str:
    """Extract page title."""
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return "Unknown"


def _extract_meta_description(soup: BeautifulSoup) -> str:
    """Extract meta description for quick company summary."""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"]
    # Try Open Graph description
    og_meta = soup.find("meta", attrs={"property": "og:description"})
    if og_meta and og_meta.get("content"):
        return og_meta["content"]
    return ""


def _extract_headings(soup: BeautifulSoup) -> list[str]:
    """Extract all headings to understand page structure and products."""
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(strip=True)
        if text and len(text) > 3 and len(text) < 200:
            headings.append(text)
    return headings


def _extract_main_content(soup: BeautifulSoup) -> str:
    """Extract main body content as text."""
    # Try to find main content area
    main = soup.find("main") or soup.find("article") or soup.find("body")
    if main:
        text = main.get_text(separator="\n", strip=True)
        # Clean up excessive whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)
    return ""


def _extract_nav_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract navigation links to understand site sections."""
    links = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if text and len(text) > 2 and len(text) < 50:
            if not href.startswith(("#", "javascript:", "mailto:")):
                links.append(text)
    # Deduplicate while preserving order
    seen = set()
    unique_links = []
    for link in links:
        if link.lower() not in seen:
            seen.add(link.lower())
            unique_links.append(link)
    return unique_links
