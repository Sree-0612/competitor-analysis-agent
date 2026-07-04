"""
CompeteIQ - Agent Orchestrator
Coordinates 5 specialized agents in a sequential pipeline using Google GenAI.

Architecture:
    RootOrchestrator (Sequential Pipeline)
    ├── Phase 1: CompanyProfiler → scrapes target URL
    ├── Phase 2: CompetitorFinder → discovers competitors via search
    ├── [HITL: User confirms competitor list]
    ├── Phase 3: CompetitorAnalyst → deep-dives each competitor
    ├── Phase 4: GapAnalyst → identifies strategic gaps
    └── Phase 5: StrategyAdvisor → generates action plan

Each agent is a specialized Gemini call with distinct system instructions
and tool access, following the multi-agent pattern from Google ADK.
"""

import json
from typing import Optional

from google import genai
from google.genai import types

from tools.scraper import scrape_website
from tools.search import search_competitors, search_company_details
from config.settings import GOOGLE_API_KEY, MODEL_NAME, APP_NAME


# --- Agent System Instructions ---
# Each agent has a focused role with specific expertise.

COMPANY_PROFILER_INSTRUCTION = """You are a Business Intelligence Analyst specializing in company profiling.
Given website data, produce a structured company profile.

OUTPUT FORMAT (respond ONLY with this JSON, no other text):
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
    "brand_positioning": "How they position themselves"
}
Be specific and factual. If data is limited, use your knowledge of the company."""

COMPETITOR_FINDER_INSTRUCTION = """You are a Market Research Specialist focused on competitive landscape mapping.
Given a company profile and search results about competitors, identify the top 4 direct competitors.

OUTPUT FORMAT (respond ONLY with this JSON, no other text):
{
    "target_company": "Name",
    "industry": "Industry",
    "competitors": [
        {"name": "Competitor 1", "url": "https://...", "reason": "Why direct competitor"},
        {"name": "Competitor 2", "url": "https://...", "reason": "Why direct competitor"},
        {"name": "Competitor 3", "url": "https://...", "reason": "Why direct competitor"},
        {"name": "Competitor 4", "url": "https://...", "reason": "Why direct competitor"}
    ],
    "market_context": "Brief competitive landscape description"
}
Only include DIRECT competitors. Be factual."""

COMPETITOR_ANALYST_INSTRUCTION = """You are a Competitive Intelligence Analyst performing deep competitor research.
Given search results about competitors, compile detailed profiles for each.

OUTPUT FORMAT (respond ONLY with this JSON, no other text):
{
    "competitor_profiles": [
        {
            "name": "Competitor Name",
            "products": ["Product 1", "Product 2"],
            "key_features": ["Feature 1", "Feature 2"],
            "usps": ["Unique strength 1", "Unique strength 2"],
            "pricing_tier": "budget/mid-range/premium/luxury",
            "strengths": ["Strength 1", "Strength 2"],
            "weaknesses": ["Weakness 1", "Weakness 2"],
            "recent_launches": ["Latest product/initiative"],
            "target_audience": "Who they serve"
        }
    ]
}
Be thorough and factual. Focus on current info (2024-2025)."""

GAP_ANALYST_INSTRUCTION = """You are a Strategic Gap Analysis Expert.
Compare the target company against competitors to identify gaps and advantages.

OUTPUT FORMAT (respond ONLY with this JSON, no other text):
{
    "gaps": [
        {
            "description": "What competitor has that you don't",
            "competitor": "Which competitor",
            "impact": "high/medium/low",
            "category": "product/pricing/technology/brand/customer/sustainability"
        }
    ],
    "advantages": [
        {
            "description": "What you have that competitors lack",
            "impact": "high/medium/low",
            "category": "product/pricing/technology/brand/customer/sustainability"
        }
    ],
    "parity_areas": ["Areas where roughly equal"],
    "overall_position": "Brief competitive standing assessment",
    "biggest_threat": "Single biggest competitive threat"
}
Be specific and actionable. Minimum 3 gaps and 2 advantages."""

STRATEGY_ADVISOR_INSTRUCTION = """You are a Chief Strategy Officer providing competitive intelligence recommendations.
Based on gap analysis, generate a prioritized strategic action plan.

OUTPUT FORMAT (respond ONLY with this JSON, no other text):
{
    "executive_summary": "2-3 sentence overview of position and key action needed",
    "recommendations": [
        {
            "priority": "HIGH/MEDIUM/LOW",
            "title": "Short action title",
            "description": "What to do and why",
            "addresses_gap": "Which gap this fixes",
            "timeline": "Quick Win (1-3 months) / Medium Term (3-6 months) / Long Term (6-12 months)",
            "expected_impact": "What improvement to expect"
        }
    ],
    "quick_wins": ["Immediate actions achievable this week"],
    "competitive_moat": "Strongest advantage and how to protect it",
    "risk_if_no_action": "What happens if gaps not addressed",
    "industry_trend_alignment": "How recommendations align with industry direction"
}
Maximum 6 recommendations. At least 1 Quick Win. Be specific, not generic."""


def _get_client() -> genai.Client:
    """Get configured GenAI client."""
    return genai.Client(api_key=GOOGLE_API_KEY)


def _call_agent(instruction: str, user_message: str) -> str:
    """
    Call a single agent (Gemini with system instruction).
    Each call represents one specialized agent in the pipeline.
    Synchronous to avoid event loop conflicts with Streamlit.
    """
    client = _get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=instruction,
            temperature=0.3,  # Low temp for factual, consistent output
        ),
    )
    return response.text or ""


# ============================================================
# PHASE 1: DISCOVERY PIPELINE
# ============================================================

def run_discovery_phase(url: str, session_id: str = "default") -> dict:
    """
    Run Phase 1: Company profiling + competitor discovery.
    Agents: CompanyProfiler → CompetitorFinder
    Returns results for HITL confirmation before proceeding.
    """
    try:
        # --- Agent 1: Company Profiler ---
        # Tool: scrape_website
        scraped_data = scrape_website(url)

        profiler_input = f"""Analyze this company website data and create a structured profile.

URL: {url}
SCRAPED DATA:
Title: {scraped_data.get('title', 'N/A')}
Description: {scraped_data.get('meta_description', 'N/A')}
Headings: {json.dumps(scraped_data.get('headings', [])[:15])}
Key Links: {json.dumps(scraped_data.get('key_links', [])[:10])}
Content Preview: {scraped_data.get('main_content', 'N/A')[:1500]}"""

        company_profile = _call_agent(COMPANY_PROFILER_INSTRUCTION, profiler_input)

        # --- Agent 2: Competitor Finder ---
        # Tool: search_competitors
        # Extract company name and industry from profile for search
        try:
            profile_data = json.loads(company_profile)
            company_name = profile_data.get("name", "")
            industry = profile_data.get("industry", "")
        except json.JSONDecodeError:
            company_name = scraped_data.get("title", "").split("|")[0].strip()
            industry = "general"

        search_results = search_competitors(company_name, industry)

        finder_input = f"""Based on this company profile and search results, identify their top 4 competitors.

COMPANY PROFILE:
{company_profile}

SEARCH RESULTS:
{json.dumps(search_results, indent=2)[:3000]}"""

        competitors_output = _call_agent(COMPETITOR_FINDER_INSTRUCTION, finder_input)

        # Combine Phase 1 outputs
        combined_output = f"""COMPANY PROFILE:
{company_profile}

---

COMPETITORS DISCOVERED:
{competitors_output}"""

        return {
            "session_id": session_id,
            "raw_output": combined_output,
            "company_profile": company_profile,
            "competitors": competitors_output,
            "success": True,
        }

    except Exception as e:
        import traceback
        return {
            "session_id": session_id,
            "raw_output": f"Discovery phase error: {type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}",
            "success": False,
        }


# ============================================================
# PHASE 2: ANALYSIS PIPELINE
# ============================================================

def run_analysis_phase(
    company_profile: str,
    competitors: str,
    session_id: str = "default",
) -> dict:
    """
    Run Phase 2: Deep analysis + gap identification + strategy.
    Agents: CompetitorAnalyst → GapAnalyst → StrategyAdvisor
    Called after HITL confirmation of competitor list.
    """
    try:
        # --- Agent 3: Competitor Analyst ---
        # Tool: search_company_details
        # Search for details on each confirmed competitor
        competitor_names = []
        try:
            comp_list = json.loads(competitors) if isinstance(competitors, str) else competitors
            if isinstance(comp_list, list):
                competitor_names = comp_list
            elif isinstance(comp_list, dict) and "competitors" in comp_list:
                competitor_names = [c.get("name", c) for c in comp_list["competitors"]]
        except (json.JSONDecodeError, TypeError):
            competitor_names = [c.strip() for c in competitors.split("\n") if c.strip()]

        # Search for each competitor's details
        all_search_results = {}
        for name in competitor_names[:4]:
            result = search_company_details(name)
            all_search_results[name] = result

        analyst_input = f"""Analyze these competitors in detail based on search results.

TARGET COMPANY PROFILE:
{company_profile}

COMPETITOR SEARCH RESULTS:
{json.dumps(all_search_results, indent=2)[:4000]}

Competitors to analyze: {', '.join(competitor_names)}"""

        competitor_analysis = _call_agent(COMPETITOR_ANALYST_INSTRUCTION, analyst_input)

        # --- Agent 4: Gap Analyst ---
        gap_input = f"""Compare the target company against these competitor profiles and identify gaps.

TARGET COMPANY:
{company_profile}

COMPETITOR PROFILES:
{competitor_analysis}"""

        gap_analysis = _call_agent(GAP_ANALYST_INSTRUCTION, gap_input)

        # --- Agent 5: Strategy Advisor ---
        strategy_input = f"""Based on this gap analysis, generate strategic recommendations.

COMPANY PROFILE:
{company_profile}

GAP ANALYSIS:
{gap_analysis}

COMPETITIVE CONTEXT:
Competitors analyzed: {', '.join(competitor_names)}"""

        strategy = _call_agent(STRATEGY_ADVISOR_INSTRUCTION, strategy_input)

        return {
            "session_id": session_id,
            "raw_output": strategy,
            "competitor_analysis": competitor_analysis,
            "gap_analysis": gap_analysis,
            "strategy": strategy,
            "success": True,
        }

    except Exception as e:
        import traceback
        return {
            "session_id": session_id,
            "raw_output": f"Analysis phase error: {type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}",
            "success": False,
        }


# ============================================================
# FULL PIPELINE (CLI mode, no HITL)
# ============================================================

def run_full_pipeline(url: str) -> dict:
    """
    Run the complete pipeline without HITL (used in CLI mode).
    Executes all 5 agents sequentially.
    """
    # Phase 1
    discovery = run_discovery_phase(url)
    if not discovery["success"]:
        return {"success": False, "output": discovery["raw_output"]}

    # Phase 2 (auto-confirm all competitors)
    analysis = run_analysis_phase(
        company_profile=discovery.get("company_profile", ""),
        competitors=discovery.get("competitors", ""),
    )

    return {
        "success": analysis["success"],
        "output": analysis.get("strategy", analysis["raw_output"]),
    }
