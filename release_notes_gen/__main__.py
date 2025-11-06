"""CLI entrypoint for release notes generator."""

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

try:
    from rich.console import Console
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from .csv_loader import load_csv
from .llm import (
    generate_fix_version_notes,
    generate_confluence_notes,
    generate_slack_announcement,
)
from .writer import write_outputs


def load_example_file(path: str) -> str:
    """Load example format from file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"Example file not found: {path}")
    except Exception as e:
        raise ValueError(f"Error reading example file {path}: {e}")


def main():
    """Main CLI entrypoint."""
    # Load .env if it exists
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="Generate release notes from Jira CSV exports using OpenAI"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to Jira CSV export file",
    )
    parser.add_argument(
        "--fix-version",
        required=True,
        help="Fix version string (e.g., v1.2.3)",
    )
    parser.add_argument(
        "--project",
        default="",
        help="Project code (optional)",
    )
    parser.add_argument(
        "--summary-col",
        help="Override summary column name",
    )
    parser.add_argument(
        "--description-col",
        help="Override description column name",
    )
    parser.add_argument(
        "--key-col",
        help="Override key column name",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model to use (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2000,
        help="Maximum tokens for API response (default: 2000)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Temperature for API calls (default: 0.2)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of tickets to process (0 = all)",
    )
    parser.add_argument(
        "--out-dir",
        default="./out",
        help="Output directory (default: ./out)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse CSV and show detected columns, then exit",
    )
    parser.add_argument(
        "--fix-notes-example",
        help="Path to example format file for Jira Fix Version notes",
    )
    parser.add_argument(
        "--confluence-example",
        help="Path to example format file for Confluence notes",
    )
    parser.add_argument(
        "--slack-example",
        help="Path to example format file for Slack announcement",
    )
    
    args = parser.parse_args()
    
    # Validate API key
    if not os.getenv("OPENAI_API_KEY") and not args.dry_run:
        print("ERROR: OPENAI_API_KEY environment variable not set.", file=sys.stderr)
        print("Set it or create a .env file with OPENAI_API_KEY=sk-...", file=sys.stderr)
        sys.exit(1)
    
    console = Console() if RICH_AVAILABLE else None
    
    try:
        # Load CSV
        if console:
            console.print("[bold blue]Loading CSV...[/bold blue]")
        else:
            print("Loading CSV...")
        
        tickets, detected_columns = load_csv(
            file_path=args.input,
            summary_col=args.summary_col,
            description_col=args.description_col,
            key_col=args.key_col,
            limit=args.limit,
        )
        
        # Show detected columns
        if console:
            table = Table(title="Detected Columns")
            table.add_column("Column Type", style="cyan")
            table.add_column("Column Name", style="green")
            table.add_row("Summary", detected_columns["summary"] or "Not found")
            table.add_row("Description", detected_columns["description"] or "Not found")
            table.add_row("Key", detected_columns["key"] or "Not found (optional)")
            console.print(table)
            console.print(f"\n[bold green]Loaded {len(tickets)} tickets[/bold green]")
        else:
            print(f"Detected columns:")
            print(f"  Summary: {detected_columns['summary']}")
            print(f"  Description: {detected_columns['description']}")
            print(f"  Key: {detected_columns['key'] or 'Not found (optional)'}")
            print(f"\nLoaded {len(tickets)} tickets")
        
        if args.dry_run:
            print("\nDry run complete. Exiting.")
            sys.exit(0)
        
        # Load examples
        fix_notes_example = None
        confluence_example = None
        slack_example = None
        
        if args.fix_notes_example:
            fix_notes_example = load_example_file(args.fix_notes_example)
        if args.confluence_example:
            confluence_example = load_example_file(args.confluence_example)
        if args.slack_example:
            slack_example = load_example_file(args.slack_example)
        
        # Generate notes
        if console:
            console.print("[bold blue]Generating release notes...[/bold blue]")
        else:
            print("Generating release notes...")
        
        if console:
            with console.status("[bold green]Generating Jira Fix Version notes..."):
                fix_version_content = generate_fix_version_notes(
                    tickets,
                    args.project,
                    args.fix_version,
                    args.model,
                    args.max_tokens,
                    args.temperature,
                    fix_notes_example,
                )
            console.print("[green]✓[/green] Jira Fix Version notes generated")
            
            with console.status("[bold green]Generating Confluence notes..."):
                confluence_content = generate_confluence_notes(
                    tickets,
                    args.project,
                    args.fix_version,
                    args.model,
                    args.max_tokens,
                    args.temperature,
                    confluence_example,
                )
            console.print("[green]✓[/green] Confluence notes generated")
            
            with console.status("[bold green]Generating Slack announcement..."):
                slack_content = generate_slack_announcement(
                    tickets,
                    args.project,
                    args.fix_version,
                    args.model,
                    args.max_tokens,
                    args.temperature,
                    slack_example,
                )
            console.print("[green]✓[/green] Slack announcement generated")
        else:
            print("  Generating Jira Fix Version notes...")
            fix_version_content = generate_fix_version_notes(
                tickets,
                args.project,
                args.fix_version,
                args.model,
                args.max_tokens,
                args.temperature,
                fix_notes_example,
            )
            print("  ✓ Jira Fix Version notes generated")
            
            print("  Generating Confluence notes...")
            confluence_content = generate_confluence_notes(
                tickets,
                args.project,
                args.fix_version,
                args.model,
                args.max_tokens,
                args.temperature,
                confluence_example,
            )
            print("  ✓ Confluence notes generated")
            
            print("  Generating Slack announcement...")
            slack_content = generate_slack_announcement(
                tickets,
                args.project,
                args.fix_version,
                args.model,
                args.max_tokens,
                args.temperature,
                slack_example,
            )
            print("  ✓ Slack announcement generated")
        
        # Write files
        fix_version_path, confluence_path, slack_path = write_outputs(
            args.out_dir,
            fix_version_content,
            confluence_content,
            slack_content,
        )
        
        # Success message
        if console:
            console.print(f"\n[bold green]✓ Success![/bold green]")
            console.print(f"\n[bold]Output files:[/bold]")
            console.print(f"  • {fix_version_path}")
            console.print(f"  • {confluence_path}")
            console.print(f"  • {slack_path}")
        else:
            print(f"\n✓ Success!")
            print(f"\nOutput files:")
            print(f"  • {fix_version_path}")
            print(f"  • {confluence_path}")
            print(f"  • {slack_path}")
    
    except Exception as e:
        if console:
            console.print(f"[bold red]ERROR:[/bold red] {e}", style="red")
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

