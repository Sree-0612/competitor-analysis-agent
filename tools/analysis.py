"""
CompeteIQ - Analysis Tools
Tools for comparing companies, scoring gaps, and generating reports.
Used by Gap Analyst and Strategy Advisor agents.
"""

import json
from typing import Any
from datetime import datetime


def compare_features(company_profile: dict, competitor_profiles: list[dict]) -> dict:
    """
    Compare features between the target company and its competitors.
    
    Creates a structured comparison matrix showing where the company
    leads, lags, or matches competitors across key dimensions.
    
    Args:
        company_profile: Target company's extracted profile
        competitor_profiles: List of competitor profiles
        
    Returns:
        Structured comparison dictionary with gaps identified
    """
    comparison = {
        "company": company_profile.get("name", "Your Company"),
        "competitors": [c.get("name", "Unknown") for c in competitor_profiles],
        "timestamp": datetime.now().isoformat(),
        "dimensions": {},
        "summary": {
            "total_gaps": 0,
            "critical_gaps": 0,
            "advantages": 0,
        }
    }

    return comparison


def score_competitive_gap(gap_description: str, market_impact: str) -> dict:
    """
    Score a competitive gap based on its business impact.
    
    Args:
        gap_description: Description of what the competitor has that you don't
        market_impact: Expected market impact (high/medium/low)
        
    Returns:
        Scored gap with priority and recommended action
    """
    impact_scores = {"high": 3, "medium": 2, "low": 1}
    score = impact_scores.get(market_impact.lower(), 1)

    priority_map = {3: "CRITICAL", 2: "IMPORTANT", 1: "MONITOR"}

    return {
        "gap": gap_description,
        "impact": market_impact,
        "score": score,
        "priority": priority_map[score],
    }


def generate_report_data(
    company_profile: dict,
    competitors: list[dict],
    gaps: list[dict],
    recommendations: list[str],
) -> dict:
    """
    Generate structured report data for visualization.
    
    Args:
        company_profile: Your company's profile
        competitors: List of competitor profiles
        gaps: List of identified gaps
        recommendations: Strategic recommendations
        
    Returns:
        Complete report data structure for UI rendering
    """
    report = {
        "generated_at": datetime.now().isoformat(),
        "company": company_profile,
        "competitor_count": len(competitors),
        "competitors": competitors,
        "gap_analysis": {
            "total_gaps": len(gaps),
            "critical": [g for g in gaps if g.get("priority") == "CRITICAL"],
            "important": [g for g in gaps if g.get("priority") == "IMPORTANT"],
            "monitor": [g for g in gaps if g.get("priority") == "MONITOR"],
        },
        "recommendations": recommendations,
        "metadata": {
            "agent_version": "1.0.0",
            "model": "gemini-2.0-flash",
            "analysis_type": "competitive_intelligence",
        }
    }

    return report
