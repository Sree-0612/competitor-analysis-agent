"""
CompeteIQ - Competitor Finder Agent
Agent 2: Discovers top competitors using Tavily search API.
Uses real-time web search for grounded, current competitor data.
"""

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from tools.search import search_competitors
from config.settings import MODEL_NAME, MAX_COMPETITORS


# Define search tool for ADK
search_competitors_tool = FunctionTool(func=search_competitors)

# Agent 2: Competitor Discovery
# Takes the company profile and finds real competitors via web search.
competitor_finder_agent = LlmAgent(
    name="competitor_finder",
    model=MODEL_NAME,
    instruction=f"""You are a Market Research Specialist focused on competitive landscape mapping.

YOUR TASK:
Given a company profile (name and industry from the previous agent), use the
search_competitors tool to find their top competitors.

PROCESS:
1. Extract the company name and industry from the session state
2. Call search_competitors(company_name, industry)
3. Analyze search results to identify the top {MAX_COMPETITORS} direct competitors
4. For each competitor, note their website URL and primary focus

OUTPUT FORMAT (respond in this exact JSON structure):
{{
    "target_company": "Name of the company being analyzed",
    "industry": "The industry",
    "competitors": [
        {{
            "name": "Competitor 1 Name",
            "url": "https://www.competitor1.com",
            "reason": "Why they are a direct competitor"
        }},
        {{
            "name": "Competitor 2 Name",
            "url": "https://www.competitor2.com",
            "reason": "Why they are a direct competitor"
        }}
    ],
    "market_context": "Brief description of the competitive landscape"
}}

RULES:
- Only include DIRECT competitors (same industry, similar products)
- Maximum {MAX_COMPETITORS} competitors
- Prefer well-known, established companies
- Include their actual website URLs
- Be factual - only report competitors you're confident about""",
    tools=[search_competitors_tool],
)
