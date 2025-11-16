"""CLI entrypoint for release notes generator and epic pack refiner."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv

try:
    from rich.console import Console
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    RICH_AVAILABLE = False

from release_notes_gen.csv_loader import load_csv
from release_notes_gen.llm import (
    generate_confluence_notes,
    generate_fix_version_notes,
    generate_slack_announcement,
)
from release_notes_gen.writer import write_outputs

from release_notes_gen.epic_refiner.pipeline import (
    EpicPackConfig,
    run_epic_pack_pipeline,
)
from release_notes_gen.epic_refiner.parse import EpicValidationError, parse_epic_csv


def load_example_file(path: str) -> str:
    """Load example format from file."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Example file not found: {path}") from exc
    except Exception as exc:  # pragma: no cover - IO guard
        raise ValueError(f"Error reading example file {path}: {exc}") from exc


def _ensure_api_key_available(dry_run: bool = False) -> None:
    if dry_run:
        return
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable not set.", file=sys.stderr)
        print(
            "Set it or create a .env file with OPENAI_API_KEY=sk-...",
            file=sys.stderr,
        )
        sys.exit(1)


def run_release_notes_cli(argv: Optional[Iterable[str]] = None) -> None:
    """Existing release-notes CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="release_notes_gen",
        description="Generate release notes from Jira CSV exports using OpenAI.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to Jira CSV export file.",
    )
    parser.add_argument(
        "--fix-version",
        required=True,
        help="Fix version string (e.g., v1.2.3).",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Project code (optional, defaults to 'Project').",
    )
    parser.add_argument(
        "--summary-col",
        help="Override summary column name.",
    )
    parser.add_argument(
        "--description-col",
        help="Override description column name.",
    )
    parser.add_argument(
        "--key-col",
        help="Override key column name.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model to use (default: gpt-4o-mini).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2000,
        help="Maximum tokens for API response (default: 2000).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Temperature for API calls (default: 0.2).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of tickets to process (0 = all).",
    )
    parser.add_argument(
        "--out-dir",
        default="./out",
        help="Output directory (default: ./out).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse CSV and show detected columns, then exit.",
    )
    parser.add_argument(
        "--fix-notes-example",
        help="Path to example format file for Jira Fix Version notes.",
    )
    parser.add_argument(
        "--confluence-example",
        help="Path to example format file for Confluence notes.",
    )
    parser.add_argument(
        "--slack-example",
        help="Path to example format file for Slack announcement.",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    _ensure_api_key_available(args.dry_run)

    console = Console() if RICH_AVAILABLE else None

    try:
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
            print("Detected columns:")
            print(f"  Summary: {detected_columns['summary']}")
            print(f"  Description: {detected_columns['description']}")
            print(f"  Key: {detected_columns['key'] or 'Not found (optional)'}")
            print(f"\nLoaded {len(tickets)} tickets")

        if args.dry_run:
            print("\nDry run complete. Exiting.")
            sys.exit(0)

        fix_notes_example = (
            load_example_file(args.fix_notes_example) if args.fix_notes_example else None
        )
        confluence_example = (
            load_example_file(args.confluence_example)
            if args.confluence_example
            else None
        )
        slack_example = (
            load_example_file(args.slack_example) if args.slack_example else None
        )

        project_name = (args.project or "").strip() or "Project"

        if console:
            console.print("[bold blue]Generating release notes...[/bold blue]")
        else:
            print("Generating release notes...")

        if console:
            with console.status("[bold green]Generating Jira Fix Version notes..."):
                fix_version_content = generate_fix_version_notes(
                    tickets,
                    project_name,
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
                    project_name,
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
                    project_name,
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
                project_name,
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
                project_name,
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
                project_name,
                args.fix_version,
                args.model,
                args.max_tokens,
                args.temperature,
                slack_example,
            )
            print("  ✓ Slack announcement generated")

        fix_path, confluence_path, slack_path = write_outputs(
            args.out_dir,
            fix_version_content,
            confluence_content,
            slack_content,
        )

        output_lines = [
            "",
            "✓ Success!",
            "Output files:",
            f"  • {fix_path}",
            f"  • {confluence_path}",
            f"  • {slack_path}",
        ]
        if console:
            console.print("\n[bold green]✓ Success![/bold green]")
            console.print("\n[bold]Output files:[/bold]")
            console.print(f"  • {fix_path}")
            console.print(f"  • {confluence_path}")
            console.print(f"  • {slack_path}")
        else:
            print("\n".join(output_lines))

    except Exception as exc:  # pragma: no cover - CLI
        if RICH_AVAILABLE:
            Console().print(f"[bold red]ERROR:[/bold red] {exc}", style="red")
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def run_epic_refiner_cli(argv: Optional[Iterable[str]] = None) -> None:
    """Epic pack refiner CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="release_notes_gen epic-refiner",
        description="Refine a Jira epic pack (one epic + child tickets) into markdown outputs.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to Jira CSV export containing one epic and all child tickets.",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Project code used for prompting and labelling outputs.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model to use (default: gpt-4o-mini).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (default: 0.0 for deterministic output).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1800,
        help="Maximum tokens for responses (default: 1800).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Maximum concurrent ticket refinements (default: 3).",
    )
    parser.add_argument(
        "--out-dir",
        default="./out/epic_packs",
        help="Base output directory (default: ./out/epic_packs).",
    )
    parser.add_argument(
        "--ticket-example",
        help="Path to example markdown guiding ticket outputs.",
    )
    parser.add_argument(
        "--epic-example",
        help="Path to example markdown guiding epic outputs.",
    )
    parser.add_argument(
        "--issue-key-col",
        help="Override column for Issue key.",
    )
    parser.add_argument(
        "--issue-type-col",
        help="Override column for Issue Type.",
    )
    parser.add_argument(
        "--summary-col",
        help="Override column for Summary.",
    )
    parser.add_argument(
        "--description-col",
        help="Override column for Description.",
    )
    parser.add_argument(
        "--parent-col",
        help="Override column for Parent key.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only; do not call the OpenAI API.",
    )
    parser.add_argument(
        "--squad",
        help="Optional squad context (CAT or AI).",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    _ensure_api_key_available(args.dry_run)

    console = Console() if RICH_AVAILABLE else None

    column_overrides = {
        key: value
        for key, value in {
            "issue_key": args.issue_key_col,
            "issue_type": args.issue_type_col,
            "summary": args.summary_col,
            "description": args.description_col,
            "parent_key": args.parent_col,
        }.items()
        if value
    }

    squad_arg: Optional[str] = None
    if args.squad:
        candidate = args.squad.strip().upper()
        if candidate not in {"CAT", "AI"}:
            print("Invalid squad. Allowed values: CAT, AI.", file=sys.stderr)
            sys.exit(1)
        squad_arg = candidate

    try:
        if console:
            console.print("[bold blue]Parsing epic CSV...[/bold blue]")
        else:
            print("Parsing epic CSV...")

        parse_result = parse_epic_csv(
            file_path=args.input,
            column_overrides=column_overrides or None,
        )

        epic_key = parse_result.epic.key or "(unknown)"
        children_count = len(parse_result.children)

        if console:
            table = Table(title="Epic Pack Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Epic key", epic_key)
            table.add_row("Children", str(children_count))
            table.add_row("Excluded rows", str(len(parse_result.excluded_rows)))
            table.add_row("Warnings", str(len(parse_result.warnings)))
            console.print(table)
        else:
            print(f"Epic key: {epic_key}")
            print(f"Valid children: {children_count}")
            print(f"Excluded rows: {len(parse_result.excluded_rows)}")
            print(f"Warnings: {len(parse_result.warnings)}")

        if parse_result.warnings:
            print("\nWarnings:")
            for warning in parse_result.warnings:
                print(f"  - {warning}")

        if parse_result.excluded_rows:
            print("\nExcluded rows:")
            for row in parse_result.excluded_rows:
                print(
                    f"  - Row {row.row_number}: {row.key or '(no key)'} "
                    f"({row.issue_type or 'Unknown'}) – {row.reason}"
                )

        if args.dry_run:
            print("\nDry run complete. No API calls were made.")
            sys.exit(0)

        ticket_example = (
            load_example_file(args.ticket_example) if args.ticket_example else None
        )
        epic_example = (
            load_example_file(args.epic_example) if args.epic_example else None
        )

        logs: list[str] = []

        def _log(message: str) -> None:
            logs.append(message)
            if console:
                console.log(message)
            else:
                print(message)

        config = EpicPackConfig(
            project=args.project.strip(),
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            concurrency=max(args.concurrency, 1),
            output_base_dir=args.out_dir,
            ticket_example=ticket_example,
            epic_example=epic_example,
            dry_run=False,
        )

        result = run_epic_pack_pipeline(
            file_path=args.input,
            column_overrides=column_overrides or None,
            config=config,
            progress_callback=_log,
            squad=squad_arg,
        )

        if not result.outputs:
            print("No outputs were generated.")
            sys.exit(1)

        output_dir = Path(result.outputs.output_directory)
        print("\n✓ Epic pack refinement complete.")
        print("Artefacts written to:")
        print(f"  • {output_dir / 'epic.md'}")
        print(f"  • {output_dir / 'stories.md'}")
        print(f"  • {output_dir / 'actions.md'}")
        print(f"  • {output_dir / 'suggested_new_tickets.md'}")
        print(f"  • {output_dir / 'index.md'}")
        print(f"  • {output_dir / 'refined_tickets.csv'}")
        print(f"  • {output_dir / 'pack.zip'}")

        if logs:
            print("\nRun log:")
            for entry in logs:
                print(f"  - {entry}")

    except EpicValidationError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as exc:
        print(f"File error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # pragma: no cover - CLI
        if RICH_AVAILABLE:
            Console().print(f"[bold red]ERROR:[/bold red] {exc}", style="red")
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main CLI dispatcher."""
    load_dotenv()
    argv = sys.argv[1:]

    if argv and argv[0] == "epic-refiner":
        run_epic_refiner_cli(argv[1:])
    else:
        run_release_notes_cli(argv)


if __name__ == "__main__":
    main()

