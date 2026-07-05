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
    search_industry_trends,
)
from tools.memory import save_analysis, get_previous_analysis
from config.settings import GOOGLE_API_KEY, GOOGLE_API_KEYS, MODEL_NAME, APP_NAME


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
            "social_presence": {
                "strongest_platform": "Reddit/Instagram/X/TikTok — where they have most buzz",
                "recent_buzz": "What people are talking about right now (1 sentence)"
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

STRATEGY_ADVISOR_INSTRUCTION = """You are a Chief Strategy Officer providing competitive intelligence.

FORMATTING RULES (CRITICAL — judges hate walls of text):
- Every point MUST be a single crisp sentence. Max 15 words per bullet.
- executive_summary: EXACTLY 3 bullet points, not a paragraph.
- Each recommendation play: ONE concrete sentence, not a paragraph.
- Use specific numbers, names, and dates. Never be vague.

STRATEGY RULES — this separates $100k consulting from generic AI:
1. NO generic advice. Give SPECIFIC plays with product names, features, timeframes.
   BAD:  "Improve the user interface."
   GOOD: "Launch a 15-inch OLED rear display — competitor X shipped one and Reddit users cite it as #1 switch reason."
2. Apply "Jobs to be Done" (JTBD) or "Blue Ocean Strategy" framework.
3. CITE source URLs for every factual claim.
4. Find ONE non-obvious 'Aha' insight — the single biggest lever.

OUTPUT FORMAT (respond ONLY with this JSON, no other text):
{
    "executive_summary": [
        "Bullet 1: Your market position in one sentence",
        "Bullet 2: The single biggest threat",
        "Bullet 3: The #1 action to take now"
    ],
    "aha_insight": "One surprising non-obvious insight (max 2 sentences)",
    "strategy_framework": "JTBD / Blue Ocean — one sentence on why",
    "competitor_moves": [
        {"competitor": "Name", "move": "What they just launched/changed (specific)", "date": "When", "threat_level": "high/medium/low"},
        {"competitor": "Name", "move": "Another recent move", "date": "When", "threat_level": "high/medium/low"}
    ],
    "industry_trends": [
        {"trend": "Specific trend happening NOW in this industry", "relevance": "Why it matters to you (1 sentence)", "action": "What to do about it (1 sentence)"}
    ],
    "recommendations": [
        {
            "priority": "HIGH/MEDIUM/LOW",
            "title": "5-word action title",
            "play": "ONE specific sentence: what to build/launch/change",
            "framework": "JTBD / Blue Ocean",
            "addresses_gap": "Which gap this fixes",
            "timeline": "Quick Win (1-3mo) / Medium (3-6mo) / Long (6-12mo)",
            "expected_impact": "Specific measurable outcome",
            "evidence_url": "https://source-url"
        }
    ],
    "quick_wins": ["Specific action 1 (this week)", "Specific action 2 (this week)"],
    "competitive_moat": "Your strongest advantage in one sentence",
    "risk_if_no_action": "What you lose if you don't act (specific, with timeline)",
    "sources": [
        {"claim": "Specific fact", "url": "https://source-url"}
    ]
}
Max 6 recommendations. At least 2 Quick Wins. EVERY point must be crisp, specific, evidence-backed.
NO PARAGRAPHS. Only bullet-length sentences."""


def _get_client(api_key: str = "") -> genai.Client:
    """Get configured GenAI client."""
    return genai.Client(api_key=api_key or GOOGLE_API_KEY)


# Track which key index to use next (round-robin across keys)
_current_key_index = 0


def _call_agent(instruction: str, user_message: str, max_retries: int = 3) -> str:
    """
    Call a single agent (Gemini with system instruction).
    Includes:
      - API key rotation: cycles through GOOGLE_API_KEYS on daily quota errors
      - Retry with backoff for per-minute limits (429) and server overload (503)
    """
    import time as _time
    from google.genai.errors import ClientError, ServerError

    global _current_key_index
    keys = GOOGLE_API_KEYS if GOOGLE_API_KEYS else [GOOGLE_API_KEY]
    keys_tried = 0
    last_error = None

    while keys_tried < len(keys):
        key = keys[_current_key_index % len(keys)]
        client = _get_client(key)

        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=instruction,
                        temperature=0.3,
                    ),
                )
                return response.text or ""
            except ClientError as e:
                last_error = e
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    if "PerDay" in error_str:
                        # Daily limit on this key — try next key
                        break
                    # Per-minute limit — wait and retry same key
                    wait = (2 ** attempt) * 15
                    _time.sleep(wait)
                else:
                    raise
            except ServerError as e:
                last_error = e
                wait = (2 ** attempt) * 20
                _time.sleep(wait)
        else:
            # All retries exhausted on this key without a daily-limit break
            raise last_error or RuntimeError("Agent call failed after retries.")

        # Daily limit hit on this key — rotate to next
        _current_key_index += 1
        keys_tried += 1

    # All keys exhausted
    raise RuntimeError(
        f"All {len(keys)} API key(s) hit their daily quota (20 req/day each). "
        f"Add more keys as GOOGLE_API_KEY_2, GOOGLE_API_KEY_3 in Streamlit secrets, "
        f"or wait until midnight Pacific Time for quota reset."
    )


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

        # --- Industry Trends (for trend-aware strategy) ---
        company_name, industry = _extract_name_industry(company_profile)
        trends_data = search_industry_trends(industry) if industry else {}
        trends_context = ""
        if trends_data.get("success"):
            trends_context = f"\nINDUSTRY TRENDS ({industry}):\n{trends_data.get('answer', '')[:800]}"

        strategy_input = f"""Based on this gap analysis, generate specific, evidence-backed strategic plays.

COMPANY PROFILE:
{company_profile}

GAP ANALYSIS:
{gap_analysis}

COMPETITIVE CONTEXT:
Competitors analyzed: {', '.join(competitor_names)}
{trends_context}

AVAILABLE SOURCE URLS (cite these in evidence_url / sources):
{sources_context}

REQUIREMENTS:
- Output competitor_moves: what each competitor recently launched/changed
- Output industry_trends: what's trending in this industry that the company should incorporate
- Give 3+ specific plays using JTBD or Blue Ocean framework
- ALL output must be CRISP BULLETS, not paragraphs. Max 15 words per point."""

        strategy = _call_agent(STRATEGY_ADVISOR_INSTRUCTION, strategy_input)

        # --- Persist to memory for temporal intelligence ---
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
