"""
CompeteIQ - Search Tool
Uses Tavily API (free tier) for real-time competitor discovery.
Provides grounded, current information from the web.
"""

from tavily import TavilyClient
from typing import Optional

from config.settings import TAVILY_API_KEY, MAX_SEARCH_RESULTS


def get_search_client() -> Optional[TavilyClient]:
    """Get Tavily client instance with error handling."""
    if not TAVILY_API_KEY:
        return None
    return TavilyClient(api_key=TAVILY_API_KEY)


def search_competitors(company_name: str, industry: str) -> dict:
    """
    Search for top competitors of a given company in its industry.
    
    Uses Tavily search API to find real-time competitor information.
    Falls back to structured query if initial search is insufficient.
    
    Args:
        company_name: Name of the target company
        industry: Industry/sector the company operates in
        
    Returns:
        Dictionary with search results containing competitor names and details
    """
    client = get_search_client()
    if not client:
        return {
            "success": False,
            "error": "Search API not configured. Please set TAVILY_API_KEY."
        }

    try:
        # Primary search: direct competitor query
        query = f"top competitors of {company_name} in {industry} industry 2024 2025"
        results = client.search(
            query=query,
            max_results=MAX_SEARCH_RESULTS,
            search_depth="advanced",
            include_answer=True,
        )

        return {
            "success": True,
            "query": query,
            "answer": results.get("answer", ""),
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", "")[:500],
                }
                for r in results.get("results", [])
            ],
        }

    except Exception as e:
        return {"success": False, "error": f"Search failed: {str(e)[:100]}"}


def search_company_details(company_name: str) -> dict:
    """
    Search for detailed information about a specific competitor.
    
    Retrieves latest products, features, pricing, and USPs.
    
    Args:
        company_name: Name of the competitor company
        
    Returns:
        Dictionary with detailed company information
    """
    client = get_search_client()
    if not client:
        return {"success": False, "error": "Search API not configured."}

    try:
        query = f"{company_name} latest products features pricing USP 2024 2025"
        results = client.search(
            query=query,
            max_results=5,
            search_depth="advanced",
            include_answer=True,
        )

        return {
            "success": True,
            "company": company_name,
            "answer": results.get("answer", ""),
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", "")[:500],
                }
                for r in results.get("results", [])
            ],
        }

    except Exception as e:
        return {"success": False, "error": f"Search failed: {str(e)[:100]}"}


def search_industry_trends(industry: str) -> dict:
    """
    Search for latest industry trends and market dynamics.
    
    Args:
        industry: Industry sector to research
        
    Returns:
        Dictionary with industry trend information
    """
    client = get_search_client()
    if not client:
        return {"success": False, "error": "Search API not configured."}

    try:
        query = f"{industry} industry trends market analysis 2025 emerging technologies"
        results = client.search(
            query=query,
            max_results=5,
            search_depth="basic",
            include_answer=True,
        )

        return {
            "success": True,
            "industry": industry,
            "answer": results.get("answer", ""),
            "results": [
                {
                    "title": r.get("title", ""),
                    "content": r.get("content", "")[:300],
                }
                for r in results.get("results", [])
            ],
        }

    except Exception as e:
        return {"success": False, "error": f"Search failed: {str(e)[:100]}"}


def search_social_sentiment(company_name: str) -> dict:
    """
    Mine 'alternative data' — what real customers say about a company.

    Official websites only tell you what a company WANTS you to hear.
    This searches Reddit, G2, Trustpilot, and forums to surface the
    unfiltered truth: complaints, praise, and hidden pain points that
    consultants charge thousands to uncover.

    Args:
        company_name: Name of the company to research sentiment for

    Returns:
        Dictionary with sentiment snippets and their source URLs
    """
    client = get_search_client()
    if not client:
        return {"success": False, "error": "Search API not configured."}

    try:
        # Target review/discussion platforms specifically
        query = (
            f"{company_name} reviews complaints praise "
            f"reddit OR trustpilot OR g2 OR sitejabber customer experience 2025"
        )
        results = client.search(
            query=query,
            max_results=8,
            search_depth="advanced",
            include_answer=True,
            include_domains=[
                "reddit.com", "trustpilot.com", "g2.com",
                "sitejabber.com", "capterra.com", "producthunt.com",
            ],
        )

        snippets = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:400],
                "source": _identify_platform(r.get("url", "")),
            }
            for r in results.get("results", [])
        ]

        # If domain-restricted search is thin, do a broader fallback
        if len(snippets) < 3:
            fallback = client.search(
                query=f"what do customers really think about {company_name} pros cons 2025",
                max_results=6,
                search_depth="advanced",
                include_answer=True,
            )
            for r in fallback.get("results", []):
                snippets.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", "")[:400],
                    "source": _identify_platform(r.get("url", "")),
                })

        return {
            "success": True,
            "company": company_name,
            "answer": results.get("answer", ""),
            "results": snippets,
        }

    except Exception as e:
        return {"success": False, "error": f"Sentiment search failed: {str(e)[:100]}"}


def _identify_platform(url: str) -> str:
    """Identify the review platform from a URL for source labeling."""
    url_lower = url.lower()
    if "reddit.com" in url_lower:
        return "Reddit"
    if "trustpilot.com" in url_lower:
        return "Trustpilot"
    if "g2.com" in url_lower:
        return "G2"
    if "sitejabber.com" in url_lower:
        return "SiteJabber"
    if "capterra.com" in url_lower:
        return "Capterra"
    if "producthunt.com" in url_lower:
        return "Product Hunt"
    return "Web"
