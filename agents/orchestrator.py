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
from tools.search import (
    search_competitors,
    search_company_details,
    search_social_sentiment,
)
from tools.memory import save_analysis, get_previous_analysis
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
You have TWO data sources: (1) official web search results, and (2) SOCIAL SENTIMENT
from Reddit, G2, and Trustpilot revealing what real customers actually say.

CRITICAL: Official sources tell you what a company WANTS you to hear. Social sentiment
reveals the HIDDEN TRUTH. Surface non-obvious insights (e.g. "Official site praises the UI,
but Reddit users complain it's laggy vs. competitors").

For every factual claim, cite the source URL it came from.

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
            "customer_sentiment": {
                "positive": ["What customers praise (from reviews)"],
                "negative": ["What customers complain about (from reviews)"],
                "sentiment_score": 7
            },
            "recent_launches": ["Latest product/initiative"],
            "target_audience": "Who they serve",
            "sources": ["https://url-of-a-claim", "https://another-source"]
        }
    ],
    "key_sources": [
        {"claim": "Specific factual claim made", "url": "https://source-url", "platform": "Reddit/G2/Web"}
    ]
}
Be thorough and factual. sentiment_score is 1-10. Focus on current info (2024-2025).
Populate 'sources' and 'key_sources' with REAL URLs from the provided search results."""

GAP_ANALYST_INSTRUCTION = """You are a Strategic Gap Analysis Expert.
Compare the target company against competitors to identify gaps and advantages.
Also produce a FEATURE PARITY MATRIX for a red/green comparison table.

OUTPUT FORMAT (respond ONLY with this JSON, no other text):
{
    "gaps": [
        {
            "description": "What competitor has that you don't",
            "competitor": "Which competitor",
            "impact": "high/medium/low",
            "category": "product/pricing/technology/brand/customer/sustainability",
            "source": "https://url-backing-this-claim"
        }
    ],
    "advantages": [
        {
            "description": "What you have that competitors lack",
            "impact": "high/medium/low",
            "category": "product/pricing/technology/brand/customer/sustainability"
        }
    ],
    "feature_matrix": {
        "features": ["Feature/Capability 1", "Feature 2", "Feature 3", "Feature 4", "Feature 5"],
        "companies": {
            "TargetCompanyName": [true, false, true, true, false],
            "Competitor1": [true, true, true, false, true],
            "Competitor2": [false, true, true, true, false]
        }
    },
    "parity_areas": ["Areas where roughly equal"],
    "overall_position": "Brief competitive standing assessment",
    "biggest_threat": "Single biggest competitive threat"
}
The feature_matrix booleans indicate whether each company HAS each feature (true=yes/green,
false=no/red). Use the SAME feature order for every company. Include the target company first.
Be specific and actionable. Minimum 3 gaps and 2 advantages. Attach source URLs to gaps."""

STRATEGY_ADVISOR_INSTRUCTION = """You are a Chief Strategy Officer providing competitive intelligence recommendations.
Based on gap analysis, generate a prioritized strategic action plan.

CRITICAL RULES — this is what separates a $100k consulting insight from generic AI slop:
1. DO NOT give generic advice like "improve your technology" or "enhance marketing".
   Give 3 SPECIFIC engineering or marketing 'plays' the company can execute in the next 6 months.
   BAD:  "Improve the user interface."
   GOOD: "Add a 15-inch OLED rear-passenger display because the competitor just shipped one
          and Reddit users cite it as their top reason for switching."
2. Apply a named strategy framework: "Jobs to be Done" (JTBD) or "Blue Ocean Strategy".
   State which framework each play uses.
3. GROUND every claim in evidence. When you reference a competitor fact, cite the source URL.
4. Find the 'Aha' insight — one specific, non-obvious gap that is the SINGLE biggest lever.

OUTPUT FORMAT (respond ONLY with this JSON, no other text):
{
    "executive_summary": "2-3 sentence overview of position and key action needed",
    "aha_insight": "The single most surprising, non-obvious competitive insight discovered",
    "strategy_framework": "Blue Ocean Strategy / Jobs to be Done — and why it applies here",
    "recommendations": [
        {
            "priority": "HIGH/MEDIUM/LOW",
            "title": "Short action title",
            "play": "The SPECIFIC engineering/marketing play — concrete, not generic",
            "framework": "JTBD / Blue Ocean — which framework this play uses",
            "description": "What to do and why, grounded in competitor evidence",
            "addresses_gap": "Which gap this fixes",
            "timeline": "Quick Win (1-3 months) / Medium Term (3-6 months) / Long Term (6-12 months)",
            "expected_impact": "Quantified improvement to expect",
            "evidence_url": "https://source-supporting-this-play"
        }
    ],
    "quick_wins": ["Immediate specific actions achievable this week"],
    "competitive_moat": "Strongest advantage and how to protect it",
    "risk_if_no_action": "What happens if gaps not addressed",
    "industry_trend_alignment": "How recommendations align with industry direction",
    "sources": [
        {"claim": "A specific claim used in the strategy", "url": "https://source-url"}
    ]
}
Maximum 6 recommendations. At least 1 Quick Win. Every 'play' must be specific and evidence-backed.
Populate evidence_url and sources with REAL URLs from the provided data."""


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


def _extract_name_industry(company_profile: str) -> tuple[str, str]:
    """Parse company name and industry from a profile JSON string."""
    try:
        if company_profile and "{" in company_profile:
            data = json.loads(
                company_profile[company_profile.index("{"):company_profile.rindex("}") + 1]
            )
            return data.get("name", ""), data.get("industry", "")
    except (json.JSONDecodeError, ValueError):
        pass
    return "", ""

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

        # Search for each competitor's details + social sentiment (alternative data)
        all_search_results = {}
        all_sources = []  # Collect every source URL for citations
        for name in competitor_names[:4]:
            details = search_company_details(name)
            sentiment = search_social_sentiment(name)
            all_search_results[name] = {
                "official": details,
                "social_sentiment": sentiment,
            }
            # Harvest source URLs for grounded citations
            for r in details.get("results", []):
                if r.get("url"):
                    all_sources.append({
                        "company": name,
                        "title": r.get("title", ""),
                        "url": r["url"],
                        "platform": "Web",
                    })
            for r in sentiment.get("results", []):
                if r.get("url"):
                    all_sources.append({
                        "company": name,
                        "title": r.get("title", ""),
                        "url": r["url"],
                        "platform": r.get("source", "Web"),
                    })

        analyst_input = f"""Analyze these competitors in detail using BOTH official search results
and social sentiment (Reddit/G2/Trustpilot). Surface the hidden truth customers reveal.

TARGET COMPANY PROFILE:
{company_profile}

COMPETITOR DATA (official + social sentiment):
{json.dumps(all_search_results, indent=2)[:6000]}

Competitors to analyze: {', '.join(competitor_names)}

Remember: cite REAL source URLs from the data above for your claims."""

        competitor_analysis = _call_agent(COMPETITOR_ANALYST_INSTRUCTION, analyst_input)

        # --- Agent 4: Gap Analyst ---
        gap_input = f"""Compare the target company against these competitor profiles and identify gaps.

TARGET COMPANY:
{company_profile}

COMPETITOR PROFILES:
{competitor_analysis}"""

        gap_analysis = _call_agent(GAP_ANALYST_INSTRUCTION, gap_input)

        # --- Agent 5: Strategy Advisor ---
        # Provide harvested sources so the agent can ground its claims
        sources_context = "\n".join(
            f"- [{s['platform']}] {s['title']}: {s['url']}"
            for s in all_sources[:25]
        )
        strategy_input = f"""Based on this gap analysis, generate specific, evidence-backed strategic plays.

COMPANY PROFILE:
{company_profile}

GAP ANALYSIS:
{gap_analysis}

COMPETITIVE CONTEXT:
Competitors analyzed: {', '.join(competitor_names)}

AVAILABLE SOURCE URLS (cite these in evidence_url / sources):
{sources_context}

Give 3+ specific engineering/marketing plays using a named framework. No generic advice."""

        strategy = _call_agent(STRATEGY_ADVISOR_INSTRUCTION, strategy_input)

        # --- Persist to memory for temporal intelligence ---
        company_name, industry = _extract_name_industry(company_profile)
        previous = get_previous_analysis(company_url=company_name or "unknown")
        save_analysis(
            company_url=company_name or "unknown",
            company_name=company_name,
            industry=industry,
            competitors=competitor_names,
            strategy=strategy,
            gap_analysis=gap_analysis,
        )

        return {
            "session_id": session_id,
            "raw_output": strategy,
            "competitor_analysis": competitor_analysis,
            "gap_analysis": gap_analysis,
            "strategy": strategy,
            "sources": all_sources,
            "previous_analysis": previous,
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
