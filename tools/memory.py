"""
CompeteIQ - Analysis Memory Store
Persistent local memory for temporal competitive intelligence.

Stores every analysis in a local SQLite database so the agent can answer:
    "What has changed in this market since my last run?"

This demonstrates Temporal Intelligence — the agent remembers past state
and reasons about how the competitive landscape evolves over time.

Uses only the Python standard library (sqlite3) — zero external dependencies,
zero cost, works on Streamlit Cloud's ephemeral filesystem.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


# Store DB alongside the app; Streamlit Cloud allows local writes per session.
DB_PATH = Path(__file__).parent.parent / "competeiq_memory.db"


def _get_connection() -> sqlite3.Connection:
    """Open a SQLite connection, creating the schema if needed."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analyses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company_url  TEXT NOT NULL,
            company_name TEXT,
            industry     TEXT,
            competitors  TEXT,
            strategy     TEXT,
            gap_analysis TEXT,
            created_at   TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def save_analysis(
    company_url: str,
    company_name: str,
    industry: str,
    competitors: list,
    strategy: str,
    gap_analysis: str = "",
) -> int:
    """
    Persist a completed analysis to memory.

    Returns:
        The row id of the saved analysis.
    """
    try:
        conn = _get_connection()
        cursor = conn.execute(
            """
            INSERT INTO analyses
                (company_url, company_name, industry, competitors,
                 strategy, gap_analysis, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_url,
                company_name,
                industry,
                json.dumps(competitors),
                strategy,
                gap_analysis,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid
        conn.close()
        return row_id or 0
    except Exception:
        return 0


def get_previous_analysis(company_url: str) -> Optional[dict]:
    """
    Retrieve the most recent PRIOR analysis for a company URL.

    Returns None if this is the first time analyzing this company.
    """
    try:
        conn = _get_connection()
        row = conn.execute(
            """
            SELECT * FROM analyses
            WHERE company_url = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (company_url,),
        ).fetchone()
        conn.close()
        if row:
            return {
                "id": row["id"],
                "company_url": row["company_url"],
                "company_name": row["company_name"],
                "industry": row["industry"],
                "competitors": json.loads(row["competitors"] or "[]"),
                "strategy": row["strategy"],
                "gap_analysis": row["gap_analysis"],
                "created_at": row["created_at"],
            }
        return None
    except Exception:
        return None


def get_analysis_count(company_url: str) -> int:
    """Count how many times a company URL has been analyzed."""
    try:
        conn = _get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM analyses WHERE company_url = ?",
            (company_url,),
        ).fetchone()
        conn.close()
        return row["n"] if row else 0
    except Exception:
        return 0


def list_recent_analyses(limit: int = 10) -> list[dict]:
    """List the most recent analyses across all companies (for the sidebar)."""
    try:
        conn = _get_connection()
        rows = conn.execute(
            """
            SELECT company_name, company_url, created_at
            FROM analyses
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
        return [
            {
                "company_name": r["company_name"],
                "company_url": r["company_url"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    except Exception:
        return []


def load_analysis(company_name: str) -> Optional[dict]:
    """Load the most recent full analysis for a company (for history view)."""
    try:
        conn = _get_connection()
        row = conn.execute(
            """
            SELECT * FROM analyses
            WHERE company_name = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (company_name,),
        ).fetchone()
        conn.close()
        if row:
            return {
                "company_name": row["company_name"],
                "company_url": row["company_url"],
                "industry": row["industry"],
                "competitors": json.loads(row["competitors"] or "[]"),
                "strategy": row["strategy"],
                "gap_analysis": row["gap_analysis"],
                "created_at": row["created_at"],
            }
        return None
    except Exception:
        return None


def delete_analysis(company_name: str) -> bool:
    """Delete all analyses for a company from memory."""
    try:
        conn = _get_connection()
        conn.execute("DELETE FROM analyses WHERE company_name = ?", (company_name,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False
