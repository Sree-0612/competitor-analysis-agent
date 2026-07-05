# 🎯 CompeteIQ — AI-Powered Competitive Intelligence

> Paste your company URL → get a full competitive analysis with actionable strategy in under 2 minutes.

**🔗 Live Demo:** [https://completeiq-competitor-analysis-agent.streamlit.app/](https://completeiq-competitor-analysis-agent.streamlit.app/)

> **💡 Don't want to wait?** Click any entry in the **Analysis History** sidebar (Spotify, Tesla, Starbucks) to instantly view pre-analyzed reports with full results, visualizations, and source citations.

---

## What It Does

CompeteIQ is a 5-agent AI system that delivers competitive intelligence a business owner can act on. It discovers competitors, mines customer sentiment from Reddit/G2/Trustpilot, identifies strategic gaps, and generates specific plays using JTBD/Blue Ocean frameworks — not generic advice.

---

## Architecture

```
URL Input
    │
    ▼
┌──────────────────────────────────────────────┐
│  Agent 1: Company Profiler                   │
│  Tool: Jina Reader (anti-bot, JS rendering)  │
├──────────────────────────────────────────────┤
│  Agent 2: Competitor Finder                  │
│  Tool: Tavily Search API                     │
└──────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────┐
│  🙋 HUMAN-IN-THE-LOOP GATE                   │
│  User confirms/edits/adds competitors        │
└──────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────┐
│  Agent 3: Competitor Analyst                 │
│  Tools: Search + Reddit/G2 Sentiment         │
├──────────────────────────────────────────────┤
│  Agent 4: Gap Analyst                        │
│  Output: Gaps, advantages, feature matrix    │
├──────────────────────────────────────────────┤
│  Agent 5: Strategy Advisor                   │
│  Framework: JTBD / Blue Ocean Strategy       │
└──────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────┐
│  📊 Results Dashboard                        │
│  5 tabs + PDF/JSON export + memory           │
└──────────────────────────────────────────────┘
```

---

## Competition Concepts (5/6)

| # | Concept | Implementation |
|---|---------|---------------|
| 1 | **Multi-Agent System** | 5 specialized Gemini 2.5 Flash agents in sequential pipeline |
| 2 | **MCP Server** | FastMCP with 7 tools (scrape, search, sentiment, trends, memory) |
| 3 | **Security** | SSRF prevention, rate limiting, output sanitization, no keys in code |
| 4 | **Deployability** | Streamlit Cloud (live URL) + Docker + CLI |
| 5 | **Human-in-the-Loop** | Interactive data editor — users toggle/edit/add competitors |

---

## Key Features

| Feature | Why It Matters |
|---------|---------------|
| 🧠 Jina Reader scraping | Bypasses anti-bot measures that stop 90% of scrapers |
| 🗣️ Reddit/G2/Trustpilot sentiment | Alternative data — the "hidden truth" beyond official marketing |
| 🔗 Source-grounded citations | Every claim has a clickable URL. Zero hallucinations. |
| 📈 7+ Plotly visualizations | Radar, heatmap, feature matrix, bubble chart, donut |
| 🕐 Temporal memory (SQLite) | Remembers past analyses, shows "what changed" |
| 📄 PDF + JSON export | Full multi-page report download |
| 🚨 Competitor Moves | What competitors just launched/changed |
| 📈 Industry Trends | What's trending that you should incorporate |
| 🔑 API key rotation | 4 keys auto-rotate — never hit quota limits |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Gemini 2.5 Flash (google-genai) |
| Scraping | Jina Reader → httpx + BeautifulSoup fallback |
| Search | Tavily API (free tier) |
| Sentiment | Tavily targeting Reddit, G2, Trustpilot |
| UI | Streamlit + Plotly |
| Memory | SQLite |
| PDF | fpdf2 |
| MCP | FastMCP (7 tools) |
| CLI | Typer + Rich |
| Deploy | Streamlit Cloud (free) |

---

## Quick Start

```bash
# Clone
git clone https://github.com/Sree-0612/competitor-analysis-agent.git
cd competitor-analysis-agent

# Install
pip install -r requirements.txt

# Set keys
cp .env.example .env
# Add GOOGLE_API_KEY and TAVILY_API_KEY

# Run
streamlit run app.py
```

### CLI

```bash
python cli.py analyze --url "https://www.tesla.com"
python cli.py discover --company "Nike" --industry "athletic footwear"
```

### MCP Server

```bash
python -m mcp_server.server
```

---

## Project Structure

```
competitor-analysis-agent/
├── app.py                  # Streamlit SaaS dashboard
├── cli.py                  # Typer CLI
├── evaluate.py             # Test suite
├── agents/
│   ├── __init__.py
│   └── orchestrator.py     # 5-agent pipeline + key rotation
├── tools/
│   ├── __init__.py
│   ├── scraper.py          # Jina Reader + httpx fallback
│   ├── search.py           # Tavily search + sentiment
│   ├── memory.py           # SQLite temporal store
│   ├── security.py         # SSRF, rate limiter, sanitizer
│   └── analysis.py         # Scoring utilities
├── config/
│   ├── __init__.py
│   └── settings.py         # Keys, model config
├── mcp_server/
│   ├── __init__.py
│   └── server.py           # 7 MCP tools
├── requirements.txt
├── Dockerfile
└── .streamlit/
```

---

## Security

| Feature | Protection |
|---------|-----------|
| URL validation | Blocks malformed inputs, XSS patterns |
| SSRF prevention | Blocks private IPs, localhost, internal domains |
| Rate limiting | 5 requests per session |
| Output sanitization | Redacts API keys, emails from responses |
| Secret management | All keys in env/secrets, never in code |

---

## License

MIT

---

Built for [Kaggle AI Agents Capstone 2026](https://www.kaggle.com/competitions/vibecoding-agents-capstone-project) — Agents for Business track.
