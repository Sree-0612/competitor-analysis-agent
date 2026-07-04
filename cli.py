"""
CompeteIQ - CLI Interface
Demonstrates Agent Skills / Agents CLI (Competition Concept #6).
Allows running competitor analysis from the command line.

Usage:
    python cli.py analyze --url "https://www.bmw.com"
    python cli.py discover --company "BMW" --industry "luxury automotive"
    python cli.py profile --url "https://www.tesla.com"
"""

import asyncio
import json

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from tools.security import validate_url
from tools.scraper import scrape_website
from tools.search import search_competitors, search_company_details

app = typer.Typer(
    name="competeiq",
    help="🎯 CompeteIQ - AI-Powered Competitor Analysis Agent CLI",
    add_completion=False,
)
console = Console()


@app.command()
def analyze(
    url: str = typer.Option(..., "--url", "-u", help="Company website URL to analyze"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table/json"),
):
    """Run full competitor analysis pipeline for a company URL."""
    # Validate URL
    is_valid, message = validate_url(url)
    if not is_valid:
        console.print(f"[red]❌ Error:[/red] {message}")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold blue]CompeteIQ[/bold blue] - Analyzing: {url}",
        title="🎯 Competitor Analysis",
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Run the full pipeline
        task = progress.add_task("Running full analysis pipeline...", total=None)

        from agents.orchestrator import run_full_pipeline
        result = asyncio.run(run_full_pipeline(url))

        progress.update(task, description="✅ Analysis complete!")

    if result["success"]:
        if output == "json":
            console.print_json(result["output"])
        else:
            console.print(Panel(result["output"], title="📊 Analysis Results"))
    else:
        console.print("[red]Analysis failed. Check your API keys and try again.[/red]")


@app.command()
def discover(
    company: str = typer.Option(..., "--company", "-c", help="Company name"),
    industry: str = typer.Option(..., "--industry", "-i", help="Industry sector"),
):
    """Discover competitors for a company in a specific industry."""
    console.print(f"[blue]🔍 Finding competitors for {company} in {industry}...[/blue]")

    result = search_competitors(company, industry)

    if result["success"]:
        table = Table(title=f"Competitors of {company}")
        table.add_column("Source", style="cyan")
        table.add_column("Info", style="white")

        for r in result.get("results", []):
            table.add_row(r["title"][:50], r["content"][:100])

        console.print(table)

        if result.get("answer"):
            console.print(Panel(result["answer"], title="💡 Summary"))
    else:
        console.print(f"[red]❌ {result.get('error', 'Unknown error')}[/red]")


@app.command()
def profile(
    url: str = typer.Option(..., "--url", "-u", help="Company website URL"),
):
    """Scrape and profile a single company website."""
    is_valid, message = validate_url(url)
    if not is_valid:
        console.print(f"[red]❌ Error:[/red] {message}")
        raise typer.Exit(1)

    console.print(f"[blue]🏢 Profiling: {url}[/blue]")

    result = asyncio.run(scrape_website(url))

    if result["success"]:
        table = Table(title=f"Company Profile: {result.get('title', 'Unknown')}")
        table.add_column("Field", style="cyan", width=20)
        table.add_column("Value", style="white")

        table.add_row("Title", result.get("title", "N/A"))
        table.add_row("Description", result.get("meta_description", "N/A")[:100])
        table.add_row("Key Sections", ", ".join(result.get("headings", [])[:5]))
        table.add_row("Nav Links", ", ".join(result.get("key_links", [])[:8]))

        console.print(table)
    else:
        console.print(f"[red]❌ {result.get('error', 'Scraping failed')}[/red]")


@app.command()
def version():
    """Show CompeteIQ version information."""
    console.print("[bold blue]CompeteIQ[/bold blue] v1.0.0")
    console.print("AI-Powered Competitor Analysis Agent")
    console.print("Built with Google ADK + Gemini 2.0 Flash")


if __name__ == "__main__":
    app()
