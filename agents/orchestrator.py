"""
CompeteIQ - Agent Orchestrator
Root orchestrator that coordinates all 5 agents in a sequential pipeline.
Uses Google ADK's SequentialAgent for deterministic, auditable execution.

Architecture:
    RootOrchestrator (SequentialAgent)
    ├── Phase 1: CompanyProfiler → scrapes target URL
    ├── Phase 2: CompetitorFinder → discovers competitors via search
    ├── [HITL: User confirms competitor list]
    ├── Phase 3: CompetitorAnalyst → deep-dives each competitor
    ├── Phase 4: GapAnalyst → identifies strategic gaps
    └── Phase 5: StrategyAdvisor → generates action plan
"""

import json
import asyncio
from typing import Optional

from google.adk.agents import SequentialAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google import genai

from agents.company_profiler import company_profiler_agent
from agents.competitor_finder import competitor_finder_agent
from agents.competitor_analyst import competitor_analyst_agent
from agents.gap_analyst import gap_analyst_agent
from agents.strategy_advisor import strategy_advisor_agent
from config.settings import GOOGLE_API_KEY, APP_NAME


# --- Configure Google GenAI Client ---
client = genai.Client(api_key=GOOGLE_API_KEY)


# --- Phase 1 Orchestrator: Discovery ---
# Runs company profiling and competitor finding sequentially
discovery_pipeline = SequentialAgent(
    name="discovery_pipeline",
    description="Phase 1: Discover company profile and potential competitors",
    sub_agents=[company_profiler_agent, competitor_finder_agent],
)

# --- Phase 2 Orchestrator: Analysis ---
# Runs deep analysis, gap identification, and strategy generation
analysis_pipeline = SequentialAgent(
    name="analysis_pipeline",
    description="Phase 2: Analyze competitors, identify gaps, and generate strategy",
    sub_agents=[competitor_analyst_agent, gap_analyst_agent, strategy_advisor_agent],
)

# --- Root Orchestrator ---
# Full pipeline (used in CLI mode without HITL)
root_orchestrator = SequentialAgent(
    name="compete_iq_orchestrator",
    description="CompeteIQ: Full competitor analysis pipeline",
    sub_agents=[
        company_profiler_agent,
        competitor_finder_agent,
        competitor_analyst_agent,
        gap_analyst_agent,
        strategy_advisor_agent,
    ],
)


# --- Session Management ---
session_service = InMemorySessionService()


async def run_discovery_phase(url: str, session_id: str = "default") -> dict:
    """
    Run Phase 1: Company profiling + competitor discovery.
    Returns results for HITL confirmation before proceeding.
    
    Args:
        url: Target company URL
        session_id: Unique session identifier
        
    Returns:
        Dictionary with company profile and discovered competitors
    """
    runner = Runner(
        agent=discovery_pipeline,
        app_name=APP_NAME,
        session_service=session_service,
    )

    # Create session with the URL as initial context
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=session_id,
    )

    # Send the URL as the user message to kick off the pipeline
    user_message = f"Analyze this company website and find their competitors: {url}"

    result_text = ""
    async for event in runner.run_async(
        user_id=session_id,
        session_id=session.id,
        new_message=user_message,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    result_text = part.text  # Keep the last agent's output

    return {
        "session_id": session.id,
        "raw_output": result_text,
        "success": bool(result_text),
    }


async def run_analysis_phase(
    company_profile: str,
    competitors: str,
    session_id: str = "default",
) -> dict:
    """
    Run Phase 2: Deep analysis + gap identification + strategy.
    Called after HITL confirmation of competitor list.
    
    Args:
        company_profile: JSON string of company profile from Phase 1
        competitors: JSON string of confirmed competitor list
        session_id: Session identifier for continuity
        
    Returns:
        Dictionary with full analysis results
    """
    runner = Runner(
        agent=analysis_pipeline,
        app_name=APP_NAME,
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=session_id,
    )

    # Provide context from Phase 1 + HITL confirmation
    context_message = f"""Continue the competitive analysis with these confirmed inputs:

COMPANY PROFILE:
{company_profile}

CONFIRMED COMPETITORS TO ANALYZE:
{competitors}

Now perform deep competitor analysis, identify gaps, and generate strategic recommendations."""

    result_text = ""
    async for event in runner.run_async(
        user_id=session_id,
        session_id=session.id,
        new_message=context_message,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    result_text = part.text

    return {
        "session_id": session.id,
        "raw_output": result_text,
        "success": bool(result_text),
    }


async def run_full_pipeline(url: str) -> dict:
    """
    Run the complete pipeline without HITL (used in CLI mode).
    
    Args:
        url: Target company URL
        
    Returns:
        Complete analysis results
    """
    runner = Runner(
        agent=root_orchestrator,
        app_name=APP_NAME,
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id="cli_user",
    )

    user_message = f"""Perform a complete competitor analysis for this company: {url}

Step 1: Scrape and profile the company
Step 2: Find their top competitors
Step 3: Deep-dive each competitor
Step 4: Identify competitive gaps
Step 5: Generate strategic recommendations

Provide the final output as a comprehensive JSON report."""

    result_text = ""
    async for event in runner.run_async(
        user_id="cli_user",
        session_id=session.id,
        new_message=user_message,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    result_text = part.text

    return {
        "success": bool(result_text),
        "output": result_text,
    }
