"""
CompeteIQ - Web Scraping Tool
Extracts structured information from company websites.
Uses httpx for async HTTP + BeautifulSoup for HTML parsing.
"""

import httpx
from bs4 import BeautifulSoup
from typing import Optional

from config.settings import REQUEST_TIMEOUT


async def scrape_website(url: str) -> dict:
    """
    Scrape a website and extract key business information.
    
    This tool fetches a company's website and extracts:
    - Page title and meta description
    - Main headings (product names, features)
    - Navigation links (reveals site structure)
    - Key content paragraphs
    
    Args:
        url: The website URL to scrape
        
    Returns:
        Dictionary with extracted content or error details
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; CompeteIQ/1.0; Research Bot)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            response = await client.get(url, headers=headers)
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
