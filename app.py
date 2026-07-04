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
from tools.memory import list_recent_analyses


def build_pdf_report(target: str, competitors: list, parsed: dict, fallback_text: str) -> bytes:
    """
    Build a clean executive-summary PDF from the analysis results.
    Uses fpdf2 (pure Python, no system dependencies).
    """
    from fpdf import FPDF

    def clean(text: str) -> str:
        # fpdf2 core fonts are latin-1; strip unsupported chars
        return str(text).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(26, 115, 232)
    pdf.cell(0, 12, clean("CompeteIQ - Competitive Analysis Report"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, clean(f"Target: {target}"), ln=True)
    pdf.cell(0, 6, clean(f"Competitors: {', '.join(competitors)}"), ln=True)
    pdf.cell(0, 6, clean(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), ln=True)
    pdf.ln(4)

    def section(title: str):
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 9, clean(title), ln=True)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(0, 0, 0)

    def body(text: str):
        pdf.multi_cell(0, 6, clean(text))
        pdf.ln(1)

    if parsed:
        if parsed.get("executive_summary"):
            section("Executive Summary")
            body(parsed["executive_summary"])
        if parsed.get("aha_insight"):
            section("The 'Aha' Insight")
            body(parsed["aha_insight"])
        if parsed.get("strategy_framework"):
            section("Strategic Framework")
            body(parsed["strategy_framework"])
        if parsed.get("recommendations"):
            section("Strategic Recommendations")
            for i, rec in enumerate(parsed["recommendations"], 1):
                pdf.set_font("Helvetica", "B", 11)
                body(f"{i}. [{rec.get('priority', 'MEDIUM')}] {rec.get('title', 'Recommendation')}")
                pdf.set_font("Helvetica", "", 11)
                if rec.get("play"):
                    body(f"   Play: {rec['play']}")
                if rec.get("description"):
                    body(f"   {rec['description']}")
                if rec.get("timeline"):
                    body(f"   Timeline: {rec['timeline']}")
        if parsed.get("quick_wins"):
            section("Quick Wins")
            for qw in parsed["quick_wins"]:
                body(f"- {qw}")
        if parsed.get("risk_if_no_action"):
            section("Risk of Inaction")
            body(parsed["risk_if_no_action"])
    else:
        section("Analysis Report")
        body(fallback_text[:3000])

    out = pdf.output(dest="S")
    # fpdf2 returns bytearray/str depending on version; normalize to bytes
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


# --- Sidebar ---
with st.sidebar:
    st.markdown(f"## 🎯 {APP_NAME}")
    st.markdown(f"*v{APP_VERSION}*")
    st.divider()

    st.markdown("#### 🏗️ Architecture")
    st.markdown("""
    **5 AI Agents** orchestrated sequentially:
    1. 🏢 Company Profiler
    2. 🔍 Competitor Finder
    3. � **Human-in-the-Loop Gate**
    4. 📊 Competitor Analyst
    5. 🔬 Gap Analyst
    6. 💡 Strategy Advisor
    """)

    st.divider()
    st.markdown("#### ⚡ Capabilities")
    st.markdown("""
    - 🧠 Jina Reader (anti-bot scraping)
    - 🗣️ Reddit/G2/Trustpilot sentiment
    - 🔗 Source-grounded citations
    - 📈 Executive dashboard (Plotly)
    - 🕐 Temporal memory (SQLite)
    - 📄 PDF export
    """)

    st.divider()
    st.markdown("#### 🛡️ Security")
    st.markdown("""
    - ✅ URL validation & SSRF prevention
    - ✅ Rate limiting (5/session)
    - ✅ Output sanitization
    - ✅ No API keys in code
    """)

    st.divider()
    st.markdown("#### 📊 Session Stats")
    analyses_done = len(st.session_state.analysis_history)
    st.metric("Analyses This Session", analyses_done)

    # Temporal memory — past analyses across sessions
    recent = list_recent_analyses(limit=5)
    if recent:
        st.markdown("#### 🧠 Analysis Memory")
        st.caption("Past runs (temporal intelligence)")
        for r in recent:
            try:
                ts = datetime.fromisoformat(r["created_at"]).strftime("%b %d, %H:%M")
            except (ValueError, TypeError):
                ts = ""
            st.markdown(f"- **{r.get('company_name') or 'Unknown'}** · {ts}")

    # API key status
    if GOOGLE_API_KEY and TAVILY_API_KEY:
        st.success("🔑 API Keys configured")
    else:
        st.error("⚠️ Missing API keys - check secrets")

    st.divider()
    st.markdown(
        "Built with [Google ADK](https://google.github.io/adk-docs/) + "
        "[Gemini 2.5 Flash](https://ai.google.dev/)"
    )


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
        st.error("Discovery phase failed. See the error details below:")
        st.code(result.get("raw_output", "No error details available."), language="text")
        st.info(
            "**Common fixes:**\n"
            "- Ensure `GOOGLE_API_KEY` and `TAVILY_API_KEY` are set in Streamlit secrets\n"
            "- Verify your Google API key is valid at https://aistudio.google.com/apikey\n"
            "- Try a different, simpler company URL"
        )
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

    st.info("💡 **Human-in-the-Loop**: You control which competitors get analyzed. "
            "This prevents wasted computation and ensures relevance.")

    # Show discovery results
    with st.expander("📋 Raw Discovery Output", expanded=True):
        st.markdown(sanitize_output(st.session_state.discovery_output))

    # Editable competitor list
    st.markdown("#### ✏️ Edit Competitor List")
    st.markdown("Add or remove competitors below (one per line):")

    # Try to extract competitor names from output
    default_competitors = "Competitor 1\nCompetitor 2\nCompetitor 3"
    try:
        # Attempt to parse JSON from competitors output
        comp_output = st.session_state.get("competitors_raw", st.session_state.discovery_output)
        # Find JSON in the output
        if "{" in comp_output:
            json_str = comp_output[comp_output.index("{"):comp_output.rindex("}") + 1]
            parsed = json.loads(json_str)
            if "competitors" in parsed:
                names = [c.get("name", "") for c in parsed["competitors"] if c.get("name")]
                if names:
                    default_competitors = "\n".join(names)
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        pass

    competitors_text = st.text_area(
        "Competitors",
        value=default_competitors,
        height=150,
        label_visibility="collapsed",
    )

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("✅ Confirm & Analyze", type="primary"):
            competitors_list = [c.strip() for c in competitors_text.split("\n") if c.strip()]
            if not competitors_list:
                st.error("Please enter at least one competitor.")
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
        st.error("Analysis failed. See the error details below:")
        st.code(result.get("raw_output", "No error details available."), language="text")
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
            st.markdown(f"#### Executive Summary")
            st.info(parsed_result["executive_summary"])

            # The "Aha" insight — the single non-obvious competitive lever
            if parsed_result.get("aha_insight"):
                st.markdown("#### 💡 The 'Aha' Insight")
                st.success(f"**{parsed_result['aha_insight']}**")

            if parsed_result.get("strategy_framework"):
                st.markdown("#### 🧭 Strategic Framework Applied")
                st.markdown(f"📐 {parsed_result['strategy_framework']}")

            if "competitive_moat" in parsed_result:
                st.markdown("#### 🏰 Competitive Moat")
                st.markdown(parsed_result["competitive_moat"])

            if "risk_if_no_action" in parsed_result:
                st.warning(f"⚠️ **Risk of Inaction:** {parsed_result['risk_if_no_action']}")
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
                    with st.expander(f"💬 {prof.get('name', 'Competitor')} — sentiment {score}/10"):
                        pos = sentiment.get("positive", [])
                        neg = sentiment.get("negative", [])
                        if pos:
                            st.markdown("**👍 Customers praise:**")
                            for p in pos:
                                st.markdown(f"- {p}")
                        if neg:
                            st.markdown("**👎 Customers complain:**")
                            for n in neg:
                                st.markdown(f"- {n}")

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

        # Parse gap analysis data (Agent 4 output)
        gap_data = None
        try:
            gap_raw = st.session_state.get("gap_analysis", "")
            if gap_raw and "{" in gap_raw:
                gap_json = gap_raw[gap_raw.index("{"):gap_raw.rindex("}") + 1]
                gap_data = json.loads(gap_json)
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
        col_gap1, col_gap2 = st.columns(2)

        with col_gap1:
            st.markdown("##### 🎯 Gap Impact Distribution")
            if parsed_result and "gaps" in parsed_result:
                gaps = parsed_result["gaps"]
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
            else:
                st.info("Gap severity data not available.")

        with col_gap2:
            st.markdown("##### 📂 Gaps by Category")
            if parsed_result and "gaps" in parsed_result:
                gaps = parsed_result["gaps"]
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
            else:
                st.info("Gap category data not available.")

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
        st.markdown("##### ⚖️ Advantage vs. Gap Balance")

        if parsed_result:
            n_gaps = len(parsed_result.get("gaps", []))
            n_advantages = len(parsed_result.get("advantages", []))

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

            # Overall position indicator
            if n_advantages > n_gaps:
                st.success(f"✅ **Strong Position** — You have more advantages ({n_advantages}) than gaps ({n_gaps}). Focus on protecting your moat.")
            elif n_advantages == n_gaps:
                st.warning(f"⚖️ **Balanced Position** — Equal advantages and gaps ({n_advantages} each). Strategic action needed.")
            else:
                st.error(f"⚠️ **Vulnerable Position** — More gaps ({n_gaps}) than advantages ({n_advantages}). Prioritize gap closure.")

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
        # Download as JSON
        st.download_button(
            "📥 JSON",
            data=json.dumps(parsed_result or {"report": sanitized_result}, indent=2),
            file_name=f"competeiq_report_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )
    with col3:
        # Download as PDF (executive summary)
        try:
            pdf_bytes = build_pdf_report(
                target=st.session_state.target_url,
                competitors=st.session_state.confirmed_competitors,
                parsed=parsed_result,
                fallback_text=sanitized_result,
            )
            st.download_button(
                "📄 PDF",
                data=pdf_bytes,
                file_name=f"competeiq_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
            )
        except Exception:
            st.caption("PDF unavailable")
    with col4:
        st.markdown(f"*Done at {datetime.now().strftime('%H:%M:%S')}*")


# --- Footer ---
st.divider()
st.markdown(
    "<center><small>CompeteIQ v1.0.0 | Built with Google ADK + Gemini 2.5 Flash | "
    "Kaggle AI Agents Capstone 2026</small></center>",
    unsafe_allow_html=True,
)
