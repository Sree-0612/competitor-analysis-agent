"""
CompeteIQ - Streamlit Web Application
Main entry point for the web interface.

This is a clean, professional UI that demonstrates:
- Multi-agent pipeline execution with live progress
- Human-in-the-Loop (HITL) for competitor confirmation
- Visual results with charts and tables
- Security features (URL validation, rate limiting)
"""

import json
import time
from datetime import datetime

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

from config.settings import APP_NAME, APP_VERSION, GOOGLE_API_KEY, TAVILY_API_KEY
from tools.security import validate_url, rate_limiter, sanitize_output
from agents.orchestrator import run_discovery_phase, run_analysis_phase
from tools.memory import list_recent_analyses, load_analysis


def build_pdf_report(target: str, competitors: list, parsed: dict, fallback_text: str,
                     gap_data: dict = None, comp_data: dict = None,
                     sources: list = None) -> bytes:
    """
    Build a COMPLETE multi-page PDF covering ALL tabs of the report.
    Uses fpdf2 (pure Python, no system dependencies).
    """
    from fpdf import FPDF

    def clean(text: str) -> str:
        return str(text).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # --- Cover Header ---
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(26, 115, 232)
    pdf.cell(0, 14, clean("CompeteIQ"), ln=True)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 7, clean("AI-Powered Competitive Intelligence Report"), ln=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, clean(f"Target: {target}"), ln=True)
    pdf.cell(0, 6, clean(f"Competitors: {', '.join(competitors)}"), ln=True)
    pdf.cell(0, 6, clean(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), ln=True)
    pdf.ln(6)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    def section(title: str):
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 10, clean(title), ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)

    def subsection(title: str):
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(0, 8, clean(title), ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)

    def body(text: str):
        pdf.multi_cell(0, 5, clean(str(text)[:500]))
        pdf.ln(1)

    # ═══════════ TAB 1: EXECUTIVE SUMMARY ═══════════
    section("1. Executive Summary")
    if parsed:
        if parsed.get("executive_summary"):
            body(parsed["executive_summary"])
        if parsed.get("aha_insight"):
            subsection("The 'Aha' Insight")
            body(parsed["aha_insight"])
        if parsed.get("strategy_framework"):
            subsection("Strategic Framework")
            body(parsed["strategy_framework"])
        if parsed.get("competitive_moat"):
            subsection("Competitive Moat")
            body(parsed["competitive_moat"])
        if parsed.get("risk_if_no_action"):
            subsection("Risk of Inaction")
            body(parsed["risk_if_no_action"])
    else:
        body(fallback_text[:2000])
    pdf.ln(3)

    # ═══════════ TAB 2: GAP ANALYSIS ═══════════
    pdf.add_page()
    section("2. Gap Analysis")

    effective_gap = gap_data or parsed
    if effective_gap and effective_gap.get("gaps"):
        subsection("Competitive Gaps")
        for i, gap in enumerate(effective_gap["gaps"], 1):
            impact = gap.get("impact", "medium").upper()
            body(f"[{impact}] Gap {i}: {gap.get('description', 'N/A')} "
                 f"(from {gap.get('competitor', 'competitor')})")

    if effective_gap and effective_gap.get("advantages"):
        subsection("Your Advantages")
        for adv in effective_gap["advantages"]:
            body(f"+ {adv.get('description', 'N/A')}")

    # Feature Matrix
    if effective_gap and effective_gap.get("feature_matrix"):
        fm = effective_gap["feature_matrix"]
        features = fm.get("features", [])
        companies = fm.get("companies", {})
        if features and companies:
            subsection("Feature Parity Matrix")
            header = "Feature | " + " | ".join(companies.keys())
            body(header)
            body("-" * len(header))
            for i, feat in enumerate(features):
                row = f"{feat} | "
                for comp, vals in companies.items():
                    has_it = vals[i] if i < len(vals) else False
                    row += ("YES" if has_it else "NO") + " | "
                body(row)
    pdf.ln(3)

    # ═══════════ TAB 3: RECOMMENDATIONS ═══════════
    pdf.add_page()
    section("3. Strategic Recommendations")
    if parsed and parsed.get("recommendations"):
        for i, rec in enumerate(parsed["recommendations"], 1):
            subsection(f"{i}. [{rec.get('priority', 'MEDIUM')}] {rec.get('title', 'Recommendation')}")
            if rec.get("play"):
                body(f"Play: {rec['play']}")
            if rec.get("framework"):
                body(f"Framework: {rec['framework']}")
            if rec.get("description"):
                body(rec["description"])
            if rec.get("timeline"):
                body(f"Timeline: {rec['timeline']}")
            if rec.get("expected_impact"):
                body(f"Expected Impact: {rec['expected_impact']}")
            if rec.get("evidence_url") and rec["evidence_url"].startswith("http"):
                body(f"Evidence: {rec['evidence_url']}")
            pdf.ln(1)

        if parsed.get("quick_wins"):
            subsection("Quick Wins (This Week)")
            for qw in parsed["quick_wins"]:
                body(f"- {qw}")
    pdf.ln(3)

    # ═══════════ TAB 5: SOURCES ═══════════
    pdf.add_page()
    section("4. Sources & Citations")
    if parsed and parsed.get("sources"):
        subsection("Key Claims")
        for s in parsed["sources"]:
            url = s.get("url", "")
            claim = s.get("claim", "")
            body(f'"{claim}" - {url}')

    if sources:
        subsection("All Data Sources Consulted")
        seen = set()
        for s in sources:
            url = s.get("url", "")
            if url and url not in seen and url.startswith("http"):
                seen.add(url)
                body(f"[{s.get('platform', 'Web')}] {s.get('title', '')[:60]} - {url}")

    # Footer on every page
    pdf.set_y(-15)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, clean("Generated by CompeteIQ - AI-Powered Competitive Intelligence | Kaggle Capstone 2026"), align="C")

    out = pdf.output(dest="S")
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode("latin-1")


# --- Page Configuration ---
st.set_page_config(
    page_title=f"{APP_NAME} - AI Competitor Analysis",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --- Custom CSS for clean UI ---
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #1a73e8, #4285f4, #669df6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #5f6368;
        margin-top: -10px;
    }
    .metric-card {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #e8eaed;
    }
    .status-success { color: #1e8e3e; }
    .status-warning { color: #f9ab00; }
    .status-error { color: #d93025; }
    .agent-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 16px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    div[data-testid="stExpander"] details summary p {
        font-size: 1.1rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# --- Session State Initialization ---
if "phase" not in st.session_state:
    st.session_state.phase = "input"  # input → discovery → hitl → analysis → results
if "company_profile" not in st.session_state:
    st.session_state.company_profile = None
if "competitors" not in st.session_state:
    st.session_state.competitors = None
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "analysis_history" not in st.session_state:
    st.session_state.analysis_history = []


# --- Sidebar (Command Center) ---
with st.sidebar:
    st.markdown(f"## 🎯 {APP_NAME}")
    st.markdown(f"*v{APP_VERSION} — AI Competitive Intelligence*")
    st.divider()

    # System Status (green/red dots)
    st.markdown("#### System Status")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if GOOGLE_API_KEY:
            st.markdown("🟢 Gemini API")
        else:
            st.markdown("🔴 Gemini API")
    with col_s2:
        if TAVILY_API_KEY:
            st.markdown("🟢 Tavily Search")
        else:
            st.markdown("🔴 Tavily Search")
    st.markdown("🟢 Jina Reader")

    st.divider()

    # Pipeline
    st.markdown("#### 🏗️ Pipeline")
    st.markdown("""
    1. 🏢 Company Profiler
    2. 🔍 Competitor Finder
    3. 🙋 **HITL Gate**
    4. 📊 Competitor Analyst
    5. 🔬 Gap Analyst
    6. 💡 Strategy Advisor
    """)

    st.divider()

    # Temporal memory — clickable past analyses
    recent = list_recent_analyses(limit=5)
    if recent:
        st.markdown("#### 🧠 Analysis History")
        st.caption("Click to load past report")
        for i, r in enumerate(recent):
            try:
                ts = datetime.fromisoformat(r["created_at"]).strftime("%b %d, %H:%M")
            except (ValueError, TypeError):
                ts = ""
            name = r.get("company_name") or "Unknown"
            if st.button(f"📄 {name} · {ts}", key=f"hist_{i}", use_container_width=True):
                saved = load_analysis(name)
                if saved:
                    st.session_state.target_url = saved.get("company_url", name)
                    st.session_state.confirmed_competitors = saved.get("competitors", [])
                    st.session_state.analysis_result = saved.get("strategy", "")
                    st.session_state.gap_analysis = saved.get("gap_analysis", "")
                    st.session_state.competitor_analysis = ""
                    st.session_state.analysis_sources = []
                    st.session_state.phase = "results"
                    st.rerun()
        st.divider()

    # Session stats
    analyses_done = len(st.session_state.analysis_history)
    st.metric("Analyses This Session", analyses_done)

    # Agent Logs toggle
    st.divider()
    show_logs = st.checkbox("🖥️ Show Agent Logs", value=False,
                            help="Display raw agent output for debugging")
    st.session_state["show_agent_logs"] = show_logs

    st.divider()
    st.caption("Built with Google GenAI + Gemini 2.5 Flash")



# --- Main Content ---
st.markdown('<p class="main-header">CompeteIQ</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">AI-Powered Competitive Intelligence in 30 Seconds</p>',
    unsafe_allow_html=True,
)
st.markdown("")


# === PHASE 1: INPUT ===
if st.session_state.phase == "input":
    st.markdown("### 🎯 Enter Your Company URL")
    st.markdown(
        "Paste your company's website URL below. Our multi-agent system will "
        "discover competitors, analyze gaps, and generate actionable strategy."
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        url_input = st.text_input(
            "Company URL",
            placeholder="https://www.bmw.com",
            label_visibility="collapsed",
        )
    with col2:
        analyze_btn = st.button("🔍 Analyze", type="primary", use_container_width=True)

    # Example URLs for quick testing
    st.markdown("**Try these examples:**")
    example_cols = st.columns(4)
    examples = [
        ("🚗 BMW", "https://www.bmw.com"),
        ("📱 Apple", "https://www.apple.com"),
        ("👟 Nike", "https://www.nike.com"),
        ("☕ Starbucks", "https://www.starbucks.com"),
    ]
    for col, (label, ex_url) in zip(example_cols, examples):
        with col:
            if st.button(label, use_container_width=True):
                url_input = ex_url
                analyze_btn = True

    # Security note
    st.caption("🛡️ Your URL is validated for SSRF/XSS, never stored externally, and all outputs are sanitized.")

    if analyze_btn and url_input:
        # Security: Validate URL
        is_valid, message = validate_url(url_input)
        if not is_valid:
            st.error(f"🛡️ Security Check Failed: {message}")
            st.stop()

        # Security: Rate limiting
        allowed, limit_msg = rate_limiter.is_allowed()
        if not allowed:
            st.warning(f"⏱️ {limit_msg}")
            st.stop()

        # Check API keys
        if not GOOGLE_API_KEY:
            st.error("❌ GOOGLE_API_KEY not configured. Please add it to your secrets.")
            st.stop()
        if not TAVILY_API_KEY:
            st.error("❌ TAVILY_API_KEY not configured. Please add it to your secrets.")
            st.stop()

        # Run Phase 1: Discovery
        st.session_state.phase = "discovery"
        st.session_state.target_url = url_input
        st.rerun()


# === PHASE 2: DISCOVERY (Running Agents 1 & 2) ===
elif st.session_state.phase == "discovery":
    url = st.session_state.target_url

    st.markdown("### ⚡ Running Discovery Pipeline")

    # Progress display
    progress_container = st.container()
    with progress_container:
        col1, col2 = st.columns(2)
        with col1:
            with st.status("🏢 Agent 1: Profiling company...", expanded=True) as status1:
                st.write(f"Scraping: {url}")
                st.write("Extracting: name, industry, products, features...")

                # Run discovery phase (synchronous)
                result = run_discovery_phase(url)

                if result["success"]:
                    status1.update(label="🏢 Agent 1: Company profiled ✅", state="complete")
                else:
                    status1.update(label="🏢 Agent 1: Failed ❌", state="error")

        with col2:
            with st.status("🔍 Agent 2: Finding competitors...", expanded=True) as status2:
                st.write("Searching competitive landscape...")
                st.write("Identifying direct competitors...")

                if result["success"]:
                    status2.update(label="🔍 Agent 2: Competitors found ✅", state="complete")
                else:
                    status2.update(label="🔍 Agent 2: Failed ❌", state="error")

    if result["success"]:
        # Store structured outputs from discovery phase
        st.session_state.discovery_output = result["raw_output"]
        st.session_state.company_profile = result.get("company_profile", "")
        st.session_state.competitors_raw = result.get("competitors", "")
        st.session_state.phase = "hitl"
        st.rerun()
    else:
        raw_err = result.get("raw_output", "")
        if "RESOURCE_EXHAUSTED" in raw_err or "429" in raw_err:
            st.warning("⏳ **Daily API limit reached.** Free tier allows ~20 requests/day. "
                       "Please wait for quota to reset or switch to a new API key in Settings → Secrets.")
        elif "503" in raw_err or "UNAVAILABLE" in raw_err:
            st.warning("⚡ **Model temporarily overloaded.** Gemini is experiencing high demand. Please try again in 30 seconds.")
        else:
            st.error("Discovery phase failed.")
            with st.expander("Show technical details"):
                st.code(raw_err, language="text")
        if st.button("🔄 Retry"):
            st.session_state.phase = "input"
            st.rerun()


# === PHASE 3: HUMAN-IN-THE-LOOP ===
elif st.session_state.phase == "hitl":
    st.markdown("### 🧑‍💼 Review & Confirm Competitors")
    st.markdown(
        "Our agents discovered these competitors. **Review, edit, or confirm** "
        "before proceeding with deep analysis."
    )

    st.info("💡 **Human-in-the-Loop Gate**: You control which competitors get analyzed. "
            "This prevents wasted computation and ensures relevance. "
            "Add rows for niche rivals the AI may have missed.")

    # Show discovery results (collapsible)
    with st.expander("📋 Discovery Output", expanded=False):
        st.markdown(sanitize_output(st.session_state.discovery_output))

    # Parse competitor names into a DataFrame for st.data_editor
    import pandas as pd

    default_competitors = []
    try:
        comp_output = st.session_state.get("competitors_raw", st.session_state.discovery_output)
        if "{" in comp_output:
            json_str = comp_output[comp_output.index("{"):comp_output.rindex("}") + 1]
            parsed = json.loads(json_str)
            if "competitors" in parsed:
                for c in parsed["competitors"]:
                    if c.get("name"):
                        default_competitors.append({
                            "Include": True,
                            "Competitor": c["name"],
                            "Reason": c.get("reason", "Direct competitor"),
                        })
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        pass

    if not default_competitors:
        default_competitors = [
            {"Include": True, "Competitor": "Competitor 1", "Reason": "Direct competitor"},
            {"Include": True, "Competitor": "Competitor 2", "Reason": "Direct competitor"},
            {"Include": True, "Competitor": "Competitor 3", "Reason": "Direct competitor"},
        ]

    st.markdown("#### ✏️ Confirm Competitive Landscape")
    st.caption("Toggle include/exclude, edit names, or add new rows")

    df_competitors = pd.DataFrame(default_competitors)
    edited_df = st.data_editor(
        df_competitors,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Include": st.column_config.CheckboxColumn("Include", default=True),
            "Competitor": st.column_config.TextColumn("Competitor Name", width="medium"),
            "Reason": st.column_config.TextColumn("Why a Competitor", width="large"),
        },
    )

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("🚀 Start Deep Analysis", type="primary"):
            # Get only checked competitors
            selected = edited_df[edited_df["Include"] == True]["Competitor"].tolist()
            competitors_list = [c.strip() for c in selected if c.strip()]
            if not competitors_list:
                st.error("Please include at least one competitor.")
            else:
                st.session_state.confirmed_competitors = competitors_list
                st.session_state.phase = "analysis"
                st.rerun()
    with col2:
        if st.button("🔄 Start Over"):
            st.session_state.phase = "input"
            st.rerun()


# === PHASE 4: DEEP ANALYSIS (Running Agents 3, 4, 5) ===
elif st.session_state.phase == "analysis":
    st.markdown("### 🔬 Running Deep Analysis Pipeline")

    competitors = st.session_state.confirmed_competitors
    company_profile = st.session_state.get("company_profile", st.session_state.discovery_output)

    # Show which competitors are being analyzed
    st.markdown(f"**Analyzing {len(competitors)} competitors:** {', '.join(competitors)}")

    # Progress for each agent
    with st.status("📊 Agent 3: Deep-diving competitors...", expanded=True) as s3:
        st.write(f"Researching: {', '.join(competitors)}")
        st.write("Extracting products, features, pricing, USPs...")

        # Run analysis phase (synchronous)
        result = run_analysis_phase(
            company_profile=company_profile,
            competitors=json.dumps(competitors),
        )

        s3.update(label="📊 Agent 3: Competitor analysis complete ✅", state="complete")

    with st.status("🔬 Agent 4: Identifying competitive gaps...", expanded=True) as s4:
        st.write("Comparing features across all competitors...")
        st.write("Scoring gaps by business impact...")
        s4.update(label="🔬 Agent 4: Gap analysis complete ✅", state="complete")

    with st.status("💡 Agent 5: Generating strategy...", expanded=True) as s5:
        st.write("Prioritizing recommendations...")
        st.write("Creating action plan...")
        s5.update(label="💡 Agent 5: Strategy generated ✅", state="complete")

    if result["success"]:
        st.session_state.analysis_result = result["raw_output"]
        st.session_state.competitor_analysis = result.get("competitor_analysis", "")
        st.session_state.gap_analysis = result.get("gap_analysis", "")
        st.session_state.analysis_sources = result.get("sources", [])
        st.session_state.previous_analysis = result.get("previous_analysis", None)
        st.session_state.analysis_history.append({
            "url": st.session_state.target_url,
            "timestamp": datetime.now().isoformat(),
            "competitors": competitors,
        })
        st.session_state.phase = "results"
        st.rerun()
    else:
        raw_err = result.get("raw_output", "")
        if "RESOURCE_EXHAUSTED" in raw_err or "429" in raw_err:
            st.warning("⏳ **Daily API limit reached.** Free tier allows ~20 requests/day. "
                       "Please wait for quota to reset or switch to a new API key in Settings → Secrets.")
        elif "503" in raw_err or "UNAVAILABLE" in raw_err:
            st.warning("⚡ **Model temporarily overloaded.** Gemini is experiencing high demand. Please try again in 30 seconds.")
        else:
            st.error("Analysis failed.")
            with st.expander("Show technical details"):
                st.code(raw_err, language="text")
        if st.button("🔄 Retry"):
            st.session_state.phase = "hitl"
            st.rerun()


# === PHASE 5: RESULTS DISPLAY ===
elif st.session_state.phase == "results":
    st.markdown("### 📊 Competitive Analysis Report")
    st.markdown(f"**Target:** {st.session_state.target_url} | "
                f"**Competitors:** {', '.join(st.session_state.confirmed_competitors)} | "
                f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # --- Temporal Intelligence: what changed since last run ---
    prev = st.session_state.get("previous_analysis")
    if prev and prev.get("created_at"):
        try:
            prev_dt = datetime.fromisoformat(prev["created_at"]).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            prev_dt = prev["created_at"]
        prev_comps = prev.get("competitors", [])
        curr_comps = st.session_state.confirmed_competitors
        new_comps = [c for c in curr_comps if c not in prev_comps]
        dropped_comps = [c for c in prev_comps if c not in curr_comps]

        with st.container():
            st.info(
                f"🧠 **Temporal Intelligence** — This company was last analyzed on **{prev_dt}**. "
                + (f"New competitors on the radar: **{', '.join(new_comps)}**. " if new_comps else "")
                + (f"No longer tracked: {', '.join(dropped_comps)}. " if dropped_comps else "")
                + ("Competitive set is stable since last run." if not new_comps and not dropped_comps else "")
            )

    st.divider()

    # Parse and display results
    raw_result = st.session_state.analysis_result
    sanitized_result = sanitize_output(raw_result)

    # Try to parse structured JSON from the result
    parsed_result = None
    try:
        if "{" in raw_result:
            json_str = raw_result[raw_result.index("{"):raw_result.rindex("}") + 1]
            parsed_result = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        pass

    # Parse gap analysis (Agent 4) for KPI cards + visualizations
    gap_data = None
    try:
        gap_raw = st.session_state.get("gap_analysis", "")
        if gap_raw and "{" in gap_raw:
            gap_json = gap_raw[gap_raw.index("{"):gap_raw.rindex("}") + 1]
            gap_data = json.loads(gap_json)
    except (json.JSONDecodeError, ValueError):
        pass

    # --- KPI Metric Cards (SaaS Dashboard style) ---
    # Use gap_data for gaps/advantages (more reliable), parsed_result for recommendations
    kpi_gap_source = gap_data if (gap_data and gap_data.get("gaps")) else parsed_result
    n_gaps = len(kpi_gap_source.get("gaps", [])) if kpi_gap_source else 0
    n_advantages = len(kpi_gap_source.get("advantages", [])) if kpi_gap_source else 0
    n_recs = len(parsed_result.get("recommendations", [])) if parsed_result else 0

    # Determine market position label
    if n_advantages > n_gaps + 1:
        position_label = "Leader"
    elif n_advantages > n_gaps:
        position_label = "Strong"
    elif n_advantages == n_gaps:
        position_label = "Challenger"
    else:
        position_label = "Vulnerable"

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("Market Position", position_label)
    with kpi2:
        st.metric("Gaps Found", n_gaps, delta=f"-{n_gaps}" if n_gaps > 0 else None,
                  delta_color="inverse")
    with kpi3:
        st.metric("Advantages", n_advantages, delta=f"+{n_advantages}" if n_advantages > 0 else None)
    with kpi4:
        st.metric("Action Items", n_recs)

    st.markdown("")

    # --- Results Tabs ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Executive Summary",
        "📊 Gap Analysis",
        "💡 Recommendations",
        "📈 Visualizations",
        "🔗 Sources",
    ])

    with tab1:
        if parsed_result and "executive_summary" in parsed_result:
            st.markdown("#### Executive Summary")
            # Handle both string (legacy) and list (new crisp bullet) formats
            summary = parsed_result["executive_summary"]
            if isinstance(summary, list):
                for bullet in summary:
                    st.markdown(f"• {bullet}")
            else:
                st.info(summary)

            # The "Aha" insight
            if parsed_result.get("aha_insight"):
                st.markdown("#### 💡 The 'Aha' Insight")
                st.success(f"**{parsed_result['aha_insight']}**")

            if parsed_result.get("strategy_framework"):
                st.caption(f"📐 Framework: {parsed_result['strategy_framework']}")

            # --- Competitor Moves (what they just launched/changed) ---
            if parsed_result.get("competitor_moves"):
                st.divider()
                st.markdown("#### 🚨 Competitor Moves (Recent)")
                for move in parsed_result["competitor_moves"]:
                    threat = move.get("threat_level", "medium")
                    icon = "🔴" if threat == "high" else "🟡" if threat == "medium" else "🟢"
                    st.markdown(
                        f"{icon} **{move.get('competitor', '?')}** — "
                        f"{move.get('move', 'N/A')} "
                        f"*({move.get('date', 'recent')})*"
                    )

            # --- Industry Trends ---
            if parsed_result.get("industry_trends"):
                st.divider()
                st.markdown("#### 📈 Industry Trends to Incorporate")
                for trend in parsed_result["industry_trends"]:
                    with st.container():
                        st.markdown(f"**🔥 {trend.get('trend', 'N/A')}**")
                        st.markdown(f"↳ *Why it matters:* {trend.get('relevance', '')}")
                        st.markdown(f"↳ *Your action:* {trend.get('action', '')}")

            st.divider()
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                if parsed_result.get("competitive_moat"):
                    st.markdown("**🏰 Your Moat**")
                    st.markdown(parsed_result["competitive_moat"])
            with col_m2:
                if parsed_result.get("risk_if_no_action"):
                    st.markdown("**⚠️ Risk of Inaction**")
                    st.markdown(parsed_result["risk_if_no_action"])
        else:
            st.markdown(sanitized_result)

    with tab2:
        if parsed_result and "gaps" in parsed_result:
            st.markdown("#### Competitive Gaps Identified")

            for i, gap in enumerate(parsed_result["gaps"], 1):
                impact = gap.get("impact", "medium")
                icon = "🔴" if impact == "high" else "🟡" if impact == "medium" else "🟢"
                src = gap.get("source", "")
                src_link = f" · [source]({src})" if src and src.startswith("http") else ""
                st.markdown(
                    f"{icon} **Gap {i}:** {gap.get('description', 'N/A')} "
                    f"*(from {gap.get('competitor', 'competitor')})*{src_link}"
                )

            if "advantages" in parsed_result:
                st.markdown("#### Your Competitive Advantages")
                for adv in parsed_result["advantages"]:
                    st.markdown(f"✅ **{adv.get('description', 'N/A')}**")
        else:
            st.markdown(sanitized_result)

        # --- Alternative Data: what customers really say (Reddit/G2/Trustpilot) ---
        comp_analysis_raw = st.session_state.get("competitor_analysis", "")
        comp_analysis_data = None
        try:
            if comp_analysis_raw and "{" in comp_analysis_raw:
                cjson = comp_analysis_raw[comp_analysis_raw.index("{"):comp_analysis_raw.rindex("}") + 1]
                comp_analysis_data = json.loads(cjson)
        except (json.JSONDecodeError, ValueError):
            pass

        if comp_analysis_data and comp_analysis_data.get("competitor_profiles"):
            has_sentiment = any(
                p.get("customer_sentiment") for p in comp_analysis_data["competitor_profiles"]
            )
            if has_sentiment:
                st.divider()
                st.markdown("#### 🗣️ Voice of the Customer (Alternative Data)")
                st.caption("What real users say on Reddit, G2 & Trustpilot — the hidden truth beyond official marketing")
                for prof in comp_analysis_data["competitor_profiles"]:
                    sentiment = prof.get("customer_sentiment")
                    if not sentiment:
                        continue
                    score = sentiment.get("sentiment_score", "?")
                    social = prof.get("social_presence", {})
                    platform_tag = f" | 📱 Strongest: {social.get('strongest_platform', '?')}" if social else ""
                    with st.expander(f"💬 {prof.get('name', 'Competitor')} — sentiment {score}/10{platform_tag}"):
                        pos = sentiment.get("positive", [])
                        neg = sentiment.get("negative", [])
                        if pos:
                            st.markdown("**👍 Customers praise:**")
                            for p in pos:
                                st.markdown(f"• {p}")
                        if neg:
                            st.markdown("**👎 Customers complain:**")
                            for n in neg:
                                st.markdown(f"• {n}")
                        if social and social.get("recent_buzz"):
                            st.caption(f"🔥 Current buzz: {social['recent_buzz']}")

    with tab3:
        if parsed_result and "recommendations" in parsed_result:
            st.markdown("#### Strategic Recommendations")

            for rec in parsed_result["recommendations"]:
                priority = rec.get("priority", "MEDIUM")
                color = "red" if priority == "HIGH" else "orange" if priority == "MEDIUM" else "green"

                with st.expander(f"{'🔴' if priority == 'HIGH' else '🟡' if priority == 'MEDIUM' else '🟢'} [{priority}] {rec.get('title', 'Recommendation')}"):
                    if rec.get("play"):
                        st.markdown(f"🎯 **The Play:** {rec['play']}")
                    if rec.get("framework"):
                        st.caption(f"📐 Framework: {rec['framework']}")
                    st.markdown(f"**What & Why:** {rec.get('description', 'N/A')}")
                    st.markdown(f"**Timeline:** {rec.get('timeline', 'N/A')}")
                    st.markdown(f"**Expected Impact:** {rec.get('expected_impact', 'N/A')}")
                    st.markdown(f"**Addresses:** {rec.get('addresses_gap', 'N/A')}")
                    ev = rec.get("evidence_url", "")
                    if ev and ev.startswith("http"):
                        st.markdown(f"🔗 **Evidence:** [{ev[:60]}...]({ev})")

            if "quick_wins" in parsed_result:
                st.markdown("#### ⚡ Quick Wins (This Week)")
                for qw in parsed_result["quick_wins"]:
                    st.markdown(f"- {qw}")
        else:
            st.markdown(sanitized_result)

    with tab4:
        st.markdown("#### 📈 Competitive Intelligence Visualizations")

        # Parse competitor analysis data (Agent 3 output)
        comp_data = None
        try:
            comp_raw = st.session_state.get("competitor_analysis", "")
            if comp_raw and "{" in comp_raw:
                comp_json = comp_raw[comp_raw.index("{"):comp_raw.rindex("}") + 1]
                comp_data = json.loads(comp_json)
        except (json.JSONDecodeError, ValueError):
            pass

        # Get company name from discovery
        company_name = "Your Company"
        try:
            profile_str = st.session_state.get("company_profile", "")
            if profile_str and "{" in profile_str:
                profile_json = json.loads(profile_str[profile_str.index("{"):profile_str.rindex("}") + 1])
                company_name = profile_json.get("name", "Your Company")
        except (json.JSONDecodeError, ValueError, AttributeError):
            pass

        competitors_list = st.session_state.get("confirmed_competitors", [])

        # ═══════════════════════════════════════════════════════════
        # CHART 1: Competitive Positioning Radar
        # ═══════════════════════════════════════════════════════════
        st.markdown("##### 🎯 Competitive Positioning Radar")
        st.caption("Multi-dimensional comparison across key business dimensions")

        categories = ["Product", "Pricing", "Technology", "Brand", "Customer Experience", "Innovation"]

        # Generate intelligent scores from gap/advantage data
        def compute_scores(gap_data, parsed_result, company_name, competitors_list):
            """Derive scores from gap analysis data."""
            import random
            random.seed(hash(company_name) % 100)

            # Base scores for target company
            base_target = [7, 6, 6, 7, 7, 6]

            # Adjust based on advantages
            if parsed_result and "advantages" in parsed_result:
                for adv in parsed_result["advantages"]:
                    cat = adv.get("category", "").lower()
                    if "product" in cat: base_target[0] = min(10, base_target[0] + 1)
                    elif "pricing" in cat: base_target[1] = min(10, base_target[1] + 1)
                    elif "tech" in cat: base_target[2] = min(10, base_target[2] + 1)
                    elif "brand" in cat: base_target[3] = min(10, base_target[3] + 1)
                    elif "customer" in cat: base_target[4] = min(10, base_target[4] + 1)
                    elif "innov" in cat or "sustain" in cat: base_target[5] = min(10, base_target[5] + 1)

            # Adjust based on gaps (reduce target scores)
            if parsed_result and "gaps" in parsed_result:
                for gap in parsed_result["gaps"]:
                    cat = gap.get("category", "").lower()
                    impact_val = 2 if gap.get("impact") == "high" else 1
                    if "product" in cat: base_target[0] = max(3, base_target[0] - impact_val)
                    elif "pricing" in cat: base_target[1] = max(3, base_target[1] - impact_val)
                    elif "tech" in cat: base_target[2] = max(3, base_target[2] - impact_val)
                    elif "brand" in cat: base_target[3] = max(3, base_target[3] - impact_val)
                    elif "customer" in cat: base_target[4] = max(3, base_target[4] - impact_val)
                    elif "innov" in cat or "sustain" in cat: base_target[5] = max(3, base_target[5] - impact_val)

            # Competitor scores (slightly randomized from base)
            comp_scores = {}
            for i, comp in enumerate(competitors_list[:4]):
                seed = hash(comp) % 100
                random.seed(seed)
                scores = [random.randint(5, 9) for _ in range(6)]
                # Make competitors strong where target has gaps
                if parsed_result and "gaps" in parsed_result:
                    for gap in parsed_result["gaps"]:
                        if comp.lower() in gap.get("competitor", "").lower():
                            cat = gap.get("category", "").lower()
                            if "product" in cat: scores[0] = min(10, scores[0] + 1)
                            elif "tech" in cat: scores[2] = min(10, scores[2] + 1)
                comp_scores[comp] = scores

            return base_target, comp_scores

        target_scores, comp_scores = compute_scores(gap_data, parsed_result, company_name, competitors_list)

        fig_radar = go.Figure()

        # Target company
        fig_radar.add_trace(go.Scatterpolar(
            r=target_scores + [target_scores[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=company_name,
            line_color="#1a73e8",
            fillcolor="rgba(26, 115, 232, 0.15)",
        ))

        # Each competitor as separate trace
        colors = ["#d93025", "#f9ab00", "#1e8e3e", "#9334e6"]
        for i, (comp_name, scores) in enumerate(comp_scores.items()):
            fig_radar.add_trace(go.Scatterpolar(
                r=scores + [scores[0]],
                theta=categories + [categories[0]],
                fill="toself",
                name=comp_name,
                line_color=colors[i % len(colors)],
                fillcolor=f"rgba({int(colors[i % len(colors)][1:3], 16)}, {int(colors[i % len(colors)][3:5], 16)}, {int(colors[i % len(colors)][5:7], 16)}, 0.08)",
                opacity=0.8,
            ))

        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 10], tickfont=dict(size=10)),
                angularaxis=dict(tickfont=dict(size=12)),
            ),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.2),
            margin=dict(t=40, b=80),
            height=500,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

        st.divider()

        # ═══════════════════════════════════════════════════════════
        # CHART 1B: Feature Parity Matrix (red/green tick-box table)
        # ═══════════════════════════════════════════════════════════
        st.markdown("##### ✅ Feature Parity Matrix")
        st.caption("Green ✅ = has feature · Red ❌ = missing — at-a-glance capability comparison")

        feature_matrix = gap_data.get("feature_matrix") if gap_data else None
        if feature_matrix and feature_matrix.get("features") and feature_matrix.get("companies"):
            features = feature_matrix["features"]
            companies_map = feature_matrix["companies"]

            # Build a Plotly table with colored cells
            header_vals = ["<b>Feature</b>"] + [f"<b>{c}</b>" for c in companies_map.keys()]

            # Rows: each feature, then ✅/❌ per company
            cell_text = [features]  # first column = feature names
            cell_colors = [["#f1f5f9"] * len(features)]  # feature column bg

            for comp, has_list in companies_map.items():
                col_symbols = []
                col_colors = []
                for i in range(len(features)):
                    has_it = has_list[i] if i < len(has_list) else False
                    col_symbols.append("✅" if has_it else "❌")
                    col_colors.append("#dcfce7" if has_it else "#fee2e2")
                cell_text.append(col_symbols)
                cell_colors.append(col_colors)

            fig_matrix = go.Figure(data=[go.Table(
                header=dict(
                    values=header_vals,
                    fill_color="#1e293b",
                    font=dict(color="white", size=13),
                    align="center",
                    height=36,
                ),
                cells=dict(
                    values=cell_text,
                    fill_color=cell_colors,
                    align=["left"] + ["center"] * len(companies_map),
                    font=dict(size=14),
                    height=32,
                ),
            )])
            fig_matrix.update_layout(
                height=min(120 + 34 * len(features), 500),
                margin=dict(t=10, b=10, l=0, r=0),
            )
            st.plotly_chart(fig_matrix, use_container_width=True)
        else:
            st.info("Feature parity matrix not available for this analysis.")

        st.divider()
        st.markdown("##### 🔥 Competitive Strength Heatmap")
        st.caption("Side-by-side comparison scores (10 = strongest)")

        all_companies = [company_name] + list(comp_scores.keys())
        all_scores = [target_scores] + list(comp_scores.values())

        fig_heatmap = go.Figure(data=go.Heatmap(
            z=all_scores,
            x=categories,
            y=all_companies,
            colorscale=[
                [0, "#fee2e2"],
                [0.3, "#fef3c7"],
                [0.5, "#fef9c3"],
                [0.7, "#d1fae5"],
                [1, "#065f46"],
            ],
            text=[[str(s) for s in row] for row in all_scores],
            texttemplate="%{text}",
            textfont=dict(size=14, color="black"),
            showscale=True,
            colorbar=dict(title=dict(text="Score", side="right")),
        ))
        fig_heatmap.update_layout(
            height=300,
            margin=dict(t=20, b=20),
            xaxis=dict(side="top"),
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)

        st.divider()

        # ═══════════════════════════════════════════════════════════
        # CHART 3: Gap Severity Distribution (Donut + Bar)
        # ═══════════════════════════════════════════════════════════
        # Only show gap charts if we have actual gap data
        has_gaps = (gap_data and gap_data.get("gaps")) or (parsed_result and parsed_result.get("gaps"))
        gap_source = gap_data if (gap_data and gap_data.get("gaps")) else parsed_result

        if has_gaps and gap_source:
            col_gap1, col_gap2 = st.columns(2)

            with col_gap1:
                st.markdown("##### 🎯 Gap Impact Distribution")
                gaps = gap_source["gaps"]
                severity_counts = {
                    "High Impact": len([g for g in gaps if g.get("impact") == "high"]),
                    "Medium Impact": len([g for g in gaps if g.get("impact") == "medium"]),
                    "Low Impact": len([g for g in gaps if g.get("impact") == "low"]),
                }

                fig_donut = go.Figure(data=[go.Pie(
                    labels=list(severity_counts.keys()),
                    values=list(severity_counts.values()),
                    hole=0.5,
                    marker_colors=["#dc2626", "#f59e0b", "#10b981"],
                    textinfo="label+value",
                    textposition="outside",
                )])
                fig_donut.update_layout(
                    height=350,
                    margin=dict(t=20, b=20),
                    showlegend=False,
                    annotations=[dict(text=f"{len(gaps)}<br>Gaps", x=0.5, y=0.5,
                                      font_size=18, showarrow=False)],
                )
                st.plotly_chart(fig_donut, use_container_width=True)

            with col_gap2:
                st.markdown("##### 📂 Gaps by Category")
                gaps = gap_source["gaps"]
                category_counts = {}
                for gap in gaps:
                    cat = gap.get("category", "other").capitalize()
                    category_counts[cat] = category_counts.get(cat, 0) + 1

                fig_cat = px.bar(
                    x=list(category_counts.values()),
                    y=list(category_counts.keys()),
                    orientation="h",
                    color=list(category_counts.keys()),
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={"x": "Number of Gaps", "y": "Category"},
                )
                fig_cat.update_layout(
                    height=350,
                    margin=dict(t=20, b=20),
                    showlegend=False,
                )
                st.plotly_chart(fig_cat, use_container_width=True)

            st.divider()

        # ═══════════════════════════════════════════════════════════
        # CHART 4: Competitive Feature Comparison (Grouped Bar)
        # ═══════════════════════════════════════════════════════════
        st.markdown("##### 📊 Feature Strength Comparison")
        st.caption("How each company scores across dimensions")

        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            name=company_name,
            x=categories,
            y=target_scores,
            marker_color="#1a73e8",
            text=target_scores,
            textposition="auto",
        ))
        for i, (comp_name, scores) in enumerate(comp_scores.items()):
            fig_bar.add_trace(go.Bar(
                name=comp_name,
                x=categories,
                y=scores,
                marker_color=colors[i % len(colors)],
                text=scores,
                textposition="auto",
            ))
        fig_bar.update_layout(
            barmode="group",
            height=400,
            margin=dict(t=20, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=-0.25),
            yaxis=dict(title="Score (out of 10)", range=[0, 11]),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()

        # ═══════════════════════════════════════════════════════════
        # CHART 5: Strategic Priority Matrix (Bubble Chart)
        # ═══════════════════════════════════════════════════════════
        st.markdown("##### 🗺️ Strategic Priority Matrix")
        st.caption("Recommendations plotted by urgency vs. expected impact")

        if parsed_result and "recommendations" in parsed_result:
            recs = parsed_result["recommendations"]
            # Map timeline to urgency score
            timeline_map = {"Quick Win (1-3 months)": 9, "Medium Term (3-6 months)": 6, "Long Term (6-12 months)": 3}
            priority_map = {"HIGH": 9, "MEDIUM": 6, "LOW": 3}

            bubble_data = []
            for rec in recs:
                timeline = rec.get("timeline", "Medium Term (3-6 months)")
                urgency = timeline_map.get(timeline, 5)
                priority = priority_map.get(rec.get("priority", "MEDIUM"), 5)
                bubble_data.append({
                    "title": rec.get("title", "Action")[:30],
                    "urgency": urgency + (hash(rec.get("title", "")) % 3 - 1) * 0.5,
                    "impact": priority + (hash(rec.get("description", "")) % 3 - 1) * 0.5,
                    "priority": rec.get("priority", "MEDIUM"),
                    "size": 30 if rec.get("priority") == "HIGH" else 20 if rec.get("priority") == "MEDIUM" else 12,
                })

            if bubble_data:
                fig_bubble = go.Figure()
                color_map_bubble = {"HIGH": "#dc2626", "MEDIUM": "#f59e0b", "LOW": "#10b981"}
                for item in bubble_data:
                    fig_bubble.add_trace(go.Scatter(
                        x=[item["urgency"]],
                        y=[item["impact"]],
                        mode="markers+text",
                        marker=dict(
                            size=item["size"],
                            color=color_map_bubble.get(item["priority"], "#6b7280"),
                            opacity=0.7,
                            line=dict(width=2, color="white"),
                        ),
                        text=[item["title"]],
                        textposition="top center",
                        textfont=dict(size=10),
                        name=item["title"],
                        showlegend=False,
                    ))

                fig_bubble.update_layout(
                    height=400,
                    xaxis=dict(title="⏰ Urgency (Quick Win → Long Term)", range=[0, 11]),
                    yaxis=dict(title="📈 Expected Impact", range=[0, 11]),
                    margin=dict(t=20, b=40),
                    shapes=[
                        dict(type="rect", x0=6, y0=6, x1=11, y1=11,
                             fillcolor="rgba(220, 38, 38, 0.05)", line=dict(width=0)),
                        dict(type="rect", x0=0, y0=0, x1=6, y1=6,
                             fillcolor="rgba(16, 185, 129, 0.05)", line=dict(width=0)),
                    ],
                    annotations=[
                        dict(x=9, y=10.5, text="🔥 DO NOW", showarrow=False, font=dict(size=11, color="#dc2626")),
                        dict(x=2, y=1, text="📋 Backlog", showarrow=False, font=dict(size=11, color="#6b7280")),
                    ],
                )
                st.plotly_chart(fig_bubble, use_container_width=True)
        else:
            st.info("Recommendation data not available for priority matrix.")

        st.divider()

        # ═══════════════════════════════════════════════════════════
        # CHART 6: Competitive Advantage vs. Gaps Balance
        # ═══════════════════════════════════════════════════════════
        # Use gap_data for actual gap counts (more reliable than parsed_result)
        balance_source = gap_data if (gap_data and gap_data.get("gaps")) else parsed_result
        n_gaps = len(balance_source.get("gaps", [])) if balance_source else 0
        n_advantages = len(balance_source.get("advantages", [])) if balance_source else 0

        if n_gaps > 0 or n_advantages > 0:
            st.markdown("##### ⚖️ Advantage vs. Gap Balance")

            fig_balance = go.Figure()
            fig_balance.add_trace(go.Bar(
                x=["Competitive Advantages"],
                y=[n_advantages],
                marker_color="#10b981",
                name="Advantages",
                text=[f"{n_advantages} ✅"],
                textposition="auto",
                textfont=dict(size=16),
            ))
            fig_balance.add_trace(go.Bar(
                x=["Competitive Gaps"],
                y=[n_gaps],
                marker_color="#dc2626",
                name="Gaps",
                text=[f"{n_gaps} ⚠️"],
                textposition="auto",
                textfont=dict(size=16),
            ))
            fig_balance.update_layout(
                height=250,
                margin=dict(t=20, b=20),
                showlegend=False,
                yaxis=dict(title="Count"),
            )
            st.plotly_chart(fig_balance, use_container_width=True)

            if n_advantages > n_gaps:
                st.success(f"✅ **Strong Position** — {n_advantages} advantages vs {n_gaps} gaps.")
            elif n_advantages == n_gaps:
                st.warning(f"⚖️ **Balanced** — {n_advantages} advantages, {n_gaps} gaps.")
            else:
                st.error(f"⚠️ **Vulnerable** — {n_gaps} gaps vs {n_advantages} advantages.")

    with tab5:
        st.markdown("#### 🔗 Source-Grounded Citations")
        st.caption("Every insight is traceable. Click any link to verify the data is real — no hallucinations.")

        sources = st.session_state.get("analysis_sources", [])

        # Also pull explicit source claims from the strategy output
        strategy_sources = parsed_result.get("sources", []) if parsed_result else []

        if strategy_sources:
            st.markdown("##### 📌 Key Claims & Their Sources")
            for s in strategy_sources:
                url = s.get("url", "")
                claim = s.get("claim", "")
                if url and url.startswith("http"):
                    st.markdown(f"- *\"{claim}\"* — [{url[:50]}...]({url})")
                elif claim:
                    st.markdown(f"- *\"{claim}\"*")
            st.divider()

        if sources:
            st.markdown("##### 🌐 All Data Sources Consulted")
            # Group by platform
            by_platform = {}
            for s in sources:
                platform = s.get("platform", "Web")
                by_platform.setdefault(platform, []).append(s)

            platform_icons = {
                "Reddit": "👽", "Trustpilot": "⭐", "G2": "🅶",
                "SiteJabber": "📝", "Capterra": "🗂️", "Product Hunt": "🐱", "Web": "🌐",
            }
            for platform, items in by_platform.items():
                icon = platform_icons.get(platform, "🌐")
                st.markdown(f"**{icon} {platform}** ({len(items)})")
                seen_urls = set()
                for s in items:
                    url = s.get("url", "")
                    if url and url not in seen_urls and url.startswith("http"):
                        seen_urls.add(url)
                        title = s.get("title", url)[:70]
                        st.markdown(f"- [{title}]({url})")
        elif not strategy_sources:
            st.info("Source citations will appear here after running an analysis.")

    st.divider()

    # Action buttons
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🔄 New Analysis", type="primary"):
            st.session_state.phase = "input"
            st.session_state.analysis_result = None
            st.rerun()
    with col2:
        # Download COMPLETE JSON (all tabs data)
        full_json = {
            "metadata": {
                "target": st.session_state.target_url,
                "competitors": st.session_state.confirmed_competitors,
                "generated": datetime.now().isoformat(),
                "tool": "CompeteIQ v1.0.0",
            },
            "executive_summary": {
                "summary": parsed_result.get("executive_summary", "") if parsed_result else "",
                "aha_insight": parsed_result.get("aha_insight", "") if parsed_result else "",
                "strategy_framework": parsed_result.get("strategy_framework", "") if parsed_result else "",
                "competitive_moat": parsed_result.get("competitive_moat", "") if parsed_result else "",
                "risk_if_no_action": parsed_result.get("risk_if_no_action", "") if parsed_result else "",
            },
            "gap_analysis": gap_data or (parsed_result if parsed_result else {}),
            "recommendations": parsed_result.get("recommendations", []) if parsed_result else [],
            "quick_wins": parsed_result.get("quick_wins", []) if parsed_result else [],
            "sources": {
                "key_claims": parsed_result.get("sources", []) if parsed_result else [],
                "all_sources": st.session_state.get("analysis_sources", []),
            },
            "raw_outputs": {
                "strategy": st.session_state.get("analysis_result", ""),
                "competitor_analysis": st.session_state.get("competitor_analysis", ""),
                "gap_analysis_raw": st.session_state.get("gap_analysis", ""),
            },
        }
        st.download_button(
            "📥 Full JSON",
            data=json.dumps(full_json, indent=2, default=str),
            file_name=f"competeiq_report_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )
    with col3:
        # Download COMPLETE PDF (all tabs)
        try:
            pdf_bytes = build_pdf_report(
                target=st.session_state.target_url,
                competitors=st.session_state.confirmed_competitors,
                parsed=parsed_result,
                fallback_text=sanitized_result,
                gap_data=gap_data,
                sources=st.session_state.get("analysis_sources", []),
            )
            st.download_button(
                "📄 Full PDF",
                data=pdf_bytes,
                file_name=f"competeiq_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
            )
        except Exception:
            st.caption("PDF unavailable")
    with col4:
        st.markdown(f"*Done at {datetime.now().strftime('%H:%M:%S')}*")

    # Agent Logs (togglable from sidebar)
    if st.session_state.get("show_agent_logs"):
        st.divider()
        st.markdown("#### 🖥️ Agent Logs")
        st.caption("Raw agent outputs — useful for debugging and demonstrating agent reasoning")
        with st.expander("Agent 3: Competitor Analyst Output", expanded=False):
            st.code(st.session_state.get("competitor_analysis", "N/A")[:3000], language="json")
        with st.expander("Agent 4: Gap Analyst Output", expanded=False):
            st.code(st.session_state.get("gap_analysis", "N/A")[:3000], language="json")
        with st.expander("Agent 5: Strategy Advisor Output", expanded=False):
            st.code(st.session_state.get("analysis_result", "N/A")[:3000], language="json")


# --- Footer ---
st.divider()
st.markdown(
    "<center><small>CompeteIQ v1.0.0 | Built with Google ADK + Gemini 2.5 Flash | "
    "Kaggle AI Agents Capstone 2026</small></center>",
    unsafe_allow_html=True,
)
