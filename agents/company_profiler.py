"""
CompeteIQ - Company Profiler Agent
Agent 1: Scrapes and analyzes the target company's website to build
a structured business profile (industry, products, features, USPs).
"""

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from tools.scraper import scrape_website
from config.settings import MODEL_NAME


# Define the scraping tool for ADK
scrape_website_tool = FunctionTool(func=scrape_website)

# Agent 1: Company Profiler
# This agent takes a URL, scrapes it, and produces a structured company profile.
company_profiler_agent = LlmAgent(
    name="company_profiler",
    model=MODEL_NAME,
    instruction="""You are a Business Intelligence Analyst specializing in company profiling.

YOUR TASK:
Given a company website URL, use the scrape_website tool to extract information,
then analyze the content to produce a structured company profile.

PROCESS:
1. Call scrape_website with the provided URL
2. Analyze the scraped content (title, headings, description, main content)
3. Identify: company name, industry, key products/services, USPs, pricing tier

OUTPUT FORMAT (respond in this exact JSON structure):
{
    "name": "Company Name",
    "url": "the URL",
    "industry": "Primary industry/sector",
    "sub_industry": "Specific niche",
    "products": ["Product 1", "Product 2", "Product 3"],
    "key_features": ["Feature 1", "Feature 2", "Feature 3"],
    "usps": ["USP 1", "USP 2", "USP 3"],
    "pricing_tier": "budget/mid-range/premium/luxury",
    "target_audience": "Description of target customers",
    "brand_positioning": "How they position themselves in the market"
}

If scraping fails, do your best with the URL domain name to identify the company
and use your knowledge to fill in what you know about them.

Be specific and factual. Do not hallucinate products that don't exist.""",
    tools=[scrape_website_tool],
)
