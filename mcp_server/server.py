"""
CompeteIQ - MCP Server
Exposes competitor analysis tools via the Model Context Protocol (MCP).
Demonstrates MCP Server (Competition Concept #2).

This allows any MCP-compatible client (Claude Desktop, ADK agents, etc.)
to connect and use our tools for competitor analysis.

Run standalone: python -m mcp_server.server
"""

from fastmcp import FastMCP

from tools.scraper import scrape_website
from tools.search import (
    search_competitors,
    search_company_details,
    search_industry_trends,
    search_social_sentiment,
)
from tools.memory import get_previous_analysis, list_recent_analyses
from tools.security import validate_url


# Initialize MCP Server
mcp = FastMCP(
    name="CompeteIQ MCP Server",
    description="AI-powered competitor analysis tools accessible via MCP protocol",
)


@mcp.tool()
def analyze_company_website(url: str) -> dict:
    """
    Scrape and analyze a company website to extract business intelligence.
    
    Args:
        url: The company website URL to analyze
        
    Returns:
        Structured data including company name, products, features, and positioning
    """
    # Security validation
    is_valid, message = validate_url(url)
    if not is_valid:
        return {"error": message}

    result = scrape_website(url)
    return result


@mcp.tool()
def find_competitors(company_name: str, industry: str) -> dict:
    """
    Discover top competitors for a given company in their industry.
    Uses real-time web search for current competitive landscape.
    
    Args:
        company_name: Name of the target company
        industry: Industry/sector the company operates in
        
    Returns:
        List of competitors with names, URLs, and competitive context
    """
    return search_competitors(company_name, industry)


@mcp.tool()
def get_company_details(company_name: str) -> dict:
    """
    Get detailed information about a specific company including
    latest products, features, pricing, and market positioning.
    
    Args:
        company_name: Name of the company to research
        
    Returns:
        Detailed company profile with products, features, and strategy
    """
    return search_company_details(company_name)


@mcp.tool()
def get_industry_trends(industry: str) -> dict:
    """
    Research current trends and dynamics in a specific industry.
    Useful for contextualizing competitive analysis.
    
    Args:
        industry: Industry sector to research
        
    Returns:
        Current trends, emerging technologies, and market dynamics
    """
    return search_industry_trends(industry)


@mcp.tool()
def get_customer_sentiment(company_name: str) -> dict:
    """
    Mine 'alternative data' — what real customers say about a company on
    Reddit, G2, and Trustpilot. Surfaces the unfiltered truth (complaints
    and praise) that official websites hide.

    Args:
        company_name: Name of the company to research sentiment for

    Returns:
        Sentiment snippets with their source URLs and platform labels
    """
    return search_social_sentiment(company_name)


@mcp.tool()
def get_temporal_intelligence(company_name: str) -> dict:
    """
    Retrieve the most recent PRIOR analysis for a company, enabling
    temporal reasoning ("what has changed since my last run?").

    Args:
        company_name: Name of the company to look up in memory

    Returns:
        The previous analysis if one exists, plus a list of recent analyses
    """
    return {
        "previous_analysis": get_previous_analysis(company_name),
        "recent_analyses": list_recent_analyses(limit=10),
    }


@mcp.resource("compete-iq://about")
def get_about() -> str:
    """Information about the CompeteIQ MCP Server."""
    return """
    CompeteIQ MCP Server v1.0.0
    
    An AI-powered competitive intelligence platform that provides:
    - Company website analysis and profiling
    - Real-time competitor discovery
    - Detailed competitor research
    - Industry trend analysis
    
    Built for the Kaggle AI Agents Capstone Project 2026.
    """


# Entry point for running the MCP server standalone
if __name__ == "__main__":
    mcp.run()
