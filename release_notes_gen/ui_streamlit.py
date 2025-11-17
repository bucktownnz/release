"""Streamlit web interface for release notes and epic pack refinement."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv

from release_notes_gen.csv_loader import load_csv
from release_notes_gen.llm import (
    generate_confluence_notes,
    generate_fix_version_notes,
    generate_slack_announcement,
    generate_core_banking_weekly_update,
)
from release_notes_gen.writer import write_outputs

from release_notes_gen.epic_refiner.pipeline import (
    PROMPT_VERSION,
    EpicPackConfig,
    EpicPackResult,
    run_epic_pack_pipeline,
)
from release_notes_gen.epic_refiner.parse import EpicValidationError, parse_epic_csv
from release_notes_gen.profiles.squads import (
    format_squad_context,
    load_squad_profile,
)
from release_notes_gen.bulk_refiner.pipeline import (
    BulkRefinerConfig,
    run_bulk_refiner_pipeline,
)
from release_notes_gen.bulk_refiner.writer import (
    refined_tickets_to_csv,
    refined_tickets_to_markdown,
    epic_audit_to_markdown,
    fix_versions_to_markdown,
)


MODEL_OPTIONS = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]


# Load .env if it exists
load_dotenv()


def load_example_from_file_or_text(
    uploaded_file: Optional[object], text_area: str
) -> Optional[str]:
    """Load example from uploaded file (preferred) or text area."""
    if uploaded_file is not None:
        try:
            content = uploaded_file.read()
            if isinstance(content, bytes):
                try:
                    return content.decode("utf-8-sig").strip()
                except UnicodeDecodeError:
                    return content.decode("utf-8").strip()
            return str(content).strip()
        except Exception as exc:  # pragma: no cover - Streamlit UI
            st.error(f"Error reading uploaded file: {exc}")
            return None

    if text_area and text_area.strip():
        return text_area.strip()

    return None


def configure_release_sidebar() -> Dict[str, Any]:
    """Render sidebar controls for release notes mode."""
    with st.sidebar:
        st.header("⚙️ Configuration")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            st.error(
                "⚠️ OPENAI_API_KEY not set. "
                "Set it in your environment or create a .env file."
            )
        else:
            st.success("✓ API key loaded")

        st.divider()

        model = st.selectbox(
            "Model",
            MODEL_OPTIONS,
            index=0,
            key="release_model",
        )

        with st.expander("🔧 Advanced Options"):
            max_tokens = st.number_input(
                "Max Tokens",
                min_value=100,
                max_value=8000,
                value=2000,
                step=100,
                key="release_max_tokens",
            )
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=0.2,
                step=0.1,
                key="release_temperature",
            )
            limit = st.number_input(
                "Limit Tickets",
                min_value=0,
                value=0,
                help="0 = process all tickets",
                key="release_limit",
            )

            st.subheader("Column Overrides")
            summary_col_override = st.text_input(
                "Summary Column",
                help="Leave empty for auto-detection",
                key="release_summary_override",
            )
            description_col_override = st.text_input(
                "Description Column",
                help="Leave empty for auto-detection",
                key="release_description_override",
            )
            key_col_override = st.text_input(
                "Key Column",
                help="Leave empty for auto-detection",
                key="release_key_override",
            )

    return {
        "api_key": api_key,
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "limit": limit,
        "summary_col_override": summary_col_override,
        "description_col_override": description_col_override,
        "key_col_override": key_col_override,
    }


def ensure_release_state() -> None:
    if "release_results" not in st.session_state:
        st.session_state.release_results = None
    if "release_runtime" not in st.session_state:
        st.session_state.release_runtime = None


def render_release_notes_tab(config: Dict[str, Any]) -> None:
    """Render the existing release notes workflow."""
    ensure_release_state()

    st.header("📤 Release Notes Input")

    uploaded_file = st.file_uploader(
        "Upload Jira CSV",
        type=["csv"],
        help="Upload a CSV file exported from Jira",
    )

    fix_version = st.text_input(
        "Fix Version *",
        placeholder="v1.2.3",
        help="Required: The fix version string",
        key="release_fix_version",
    )
    project = st.text_input(
        "Project Code",
        placeholder="CPS",
        help="Optional: Project code/name",
        key="release_project",
    )

    with st.expander("📋 Example Formats (Optional)"):
        st.markdown(
            "Provide example formats to guide the model. "
            "Uploaded files take precedence over text areas."
        )

        fix_notes_file = st.file_uploader(
            "Upload Jira notes example (.md/.txt)",
            type=["md", "txt"],
            key="release_fix_notes_file",
        )
        fix_notes_text = st.text_area(
            "Or paste example format",
            height=150,
            key="release_fix_notes_text",
            help="Markdown format",
        )

        confluence_file = st.file_uploader(
            "Upload Confluence example (.md/.txt)",
            type=["md", "txt"],
            key="release_confluence_file",
        )
        confluence_text = st.text_area(
            "Or paste example format",
            height=150,
            key="release_confluence_text",
            help="Markdown format",
        )

        slack_file = st.file_uploader(
            "Upload Slack/Teams example (.md/.txt)",
            type=["md", "txt"],
            key="release_slack_file",
        )
        slack_text = st.text_area(
            "Or paste example format",
            height=150,
            key="release_slack_text",
            help="Plain text format",
        )

    generate_button = st.button(
        "🚀 Generate Release Notes",
        type="primary",
        use_container_width=True,
    )

    st.header("📥 Release Notes Output")

    if generate_button:
        if not uploaded_file:
            st.error("Please upload a CSV file.")
            return

        if not fix_version:
            st.error("Please enter a Fix Version.")
            return

        if not config["api_key"]:
            st.error("OPENAI_API_KEY not set. Cannot generate notes.")
            return

        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".csv") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name

        try:
            with st.spinner("Loading CSV..."):
                try:
                    tickets, detected_columns = load_csv(
                        file_path=tmp_path,
                        summary_col=config["summary_col_override"] or None,
                        description_col=config["description_col_override"] or None,
                        key_col=config["key_col_override"] or None,
                        limit=config["limit"] if config["limit"] > 0 else 0,
                    )
                    st.success(f"✓ Loaded {len(tickets)} tickets")
                    st.info(
                        f"Detected columns: "
                        f"Summary='{detected_columns['summary']}', "
                        f"Description='{detected_columns['description']}', "
                        f"Key='{detected_columns['key'] or 'N/A'}'"
                    )
                except Exception as exc:
                    st.error(f"Error loading CSV: {exc}")
                    return

            fix_notes_example = load_example_from_file_or_text(
                fix_notes_file, fix_notes_text
            )
            confluence_example = load_example_from_file_or_text(
                confluence_file, confluence_text
            )
            slack_example = load_example_from_file_or_text(slack_file, slack_text)

            start_time = time.time()
            progress_bar = st.progress(0, text="Generating Jira Fix Version notes...")

            try:
                fix_version_content = generate_fix_version_notes(
                    tickets,
                    project or "Project",
                    fix_version,
                    config["model"],
                    config["max_tokens"],
                    config["temperature"],
                    fix_notes_example,
                )
                progress_bar.progress(33, text="Generating Confluence notes...")

                confluence_content = generate_confluence_notes(
                    tickets,
                    project or "Project",
                    fix_version,
                    config["model"],
                    config["max_tokens"],
                    config["temperature"],
                    confluence_example,
                )
                progress_bar.progress(66, text="Generating Slack announcement...")

                slack_content = generate_slack_announcement(
                    tickets,
                    project or "Project",
                    fix_version,
                    config["model"],
                    config["max_tokens"],
                    config["temperature"],
                    slack_example,
                )

                progress_bar.progress(100, text="Writing files...")
                elapsed_time = time.time() - start_time

                out_dir = "./out"
                write_outputs(
                    out_dir,
                    fix_version_content,
                    confluence_content,
                    slack_content,
                )

                st.session_state.release_results = {
                    "fix_version": fix_version_content,
                    "confluence": confluence_content,
                    "slack": slack_content,
                }
                st.session_state.release_runtime = {
                    "tickets_processed": len(tickets),
                    "elapsed_time": elapsed_time,
                }
                st.success("✓ Generation complete!")
            except Exception as exc:  # pragma: no cover - Streamlit UI
                st.error(f"Error generating notes: {exc}")
                st.exception(exc)
            finally:
                progress_bar.empty()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if st.session_state.release_results:
        runtime_info = st.session_state.release_runtime or {}
        st.info(
            f"Processed {runtime_info.get('tickets_processed', 0)} tickets "
            f"in {runtime_info.get('elapsed_time', 0):.2f}s"
        )

        jira_tab, confluence_tab, slack_tab = st.tabs(
            ["Jira Notes", "Confluence Notes", "Slack Announcement"]
        )

        with jira_tab:
            st.subheader("Jira Fix Version Notes")
            st.markdown(st.session_state.release_results["fix_version"])
            st.download_button(
                "Download Jira Notes",
                data=st.session_state.release_results["fix_version"],
                file_name="jira_fix_version_notes.md",
                mime="text/markdown",
            )

        with confluence_tab:
            st.subheader("Confluence Release Notes")
            st.markdown(st.session_state.release_results["confluence"])
            st.download_button(
                "Download Confluence Notes",
                data=st.session_state.release_results["confluence"],
                file_name="confluence_release_notes.md",
                mime="text/markdown",
            )

        with slack_tab:
            st.subheader("Slack/Teams Announcement")
            st.text(st.session_state.release_results["slack"])
            st.download_button(
                "Download Slack Announcement",
                data=st.session_state.release_results["slack"],
                file_name="slack_announcement.txt",
                mime="text/plain",
            )


def ensure_epic_state() -> Dict[str, Any]:
    if "epic_state" not in st.session_state:
        st.session_state.epic_state = {
            "file_bytes": None,
            "column_overrides": {},
            "parse_result": None,
            "parse_summary": {},
            "result": None,
            "logs": [],
            "ticket_example": None,
            "epic_example": None,
        }
    return st.session_state.epic_state


def render_epic_pack_tab(api_key: Optional[str]) -> None:
    """Render the Epic Pack Refiner workflow."""
    state = ensure_epic_state()

    st.header("🚀 Epic Pack Refiner")
    st.markdown(
        "Refine a Jira epic and its child tickets. Upload a CSV containing one epic and its children."
    )

    uploader_col, settings_col = st.columns([2, 1])

    with uploader_col:
        uploaded_file = st.file_uploader(
            "Upload epic pack CSV",
            type=["csv"],
            help="Export from Jira including the epic and all children.",
            key="epic_csv_file",
        )
        project_code = st.text_input(
            "Project code",
            placeholder="CPS",
            help="Used in prompts and outputs.",
            key="epic_project_code",
        )
        squad_choice = st.selectbox(
            "Squad (optional)",
            options=["None", "CAT", "AI"],
            index=0,
            help=(
                "Select the squad that owns this epic so the AI can align tickets "
                "with their mission, systems, and non-functional priorities."
            ),
            key="epic_squad_choice",
        )
        selected_squad = None if squad_choice == "None" else squad_choice
        output_dir = st.text_input(
            "Output directory",
            value="./out/epic_packs",
            help="Directory to store generated artefacts.",
            key="epic_output_dir",
        )

    with settings_col:
        model = st.selectbox(
            "Model",
            MODEL_OPTIONS,
            index=0,
            key="epic_model",
        )
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            step=0.1,
            key="epic_temperature",
        )
        max_tokens = st.number_input(
            "Max tokens",
            min_value=400,
            max_value=6000,
            value=1800,
            step=100,
            key="epic_max_tokens",
        )
        concurrency = st.number_input(
            "Concurrency cap",
            min_value=1,
            max_value=8,
            value=3,
            step=1,
            key="epic_concurrency",
        )
        force_fresh = st.checkbox(
            "Force fresh run (ignore cache)",
            value=False,
            help="Bypass cached results even if the CSV and settings are unchanged.",
            key="epic_force_fresh",
        )

    st.subheader("Column Overrides (optional)")
    col_override1, col_override2, col_override3 = st.columns(3)
    with col_override1:
        issue_key_col = st.text_input("Issue key", key="epic_issue_key_override")
        issue_type_col = st.text_input("Issue type", key="epic_issue_type_override")
    with col_override2:
        summary_col = st.text_input("Summary", key="epic_summary_override")
        description_col = st.text_input("Description", key="epic_description_override")
    with col_override3:
        parent_col = st.text_input("Parent key", key="epic_parent_override")

    if selected_squad:
        profile = load_squad_profile(selected_squad)
        if profile:
            with st.expander(
                f"Squad context: {profile.get('display_name', selected_squad)}",
                expanded=False,
            ):
                st.markdown(f"```text\n{format_squad_context(profile)}\n```")
        else:
            st.warning(
                f"No squad profile found for '{selected_squad}'. "
                "Proceeding without squad context."
            )

    with st.expander("Optional example formats"):
        st.markdown(
            "Provide example markdown to shape tone. Uploaded files take precedence."
        )
        ticket_example_file = st.file_uploader(
            "Ticket example (.md/.txt)",
            type=["md", "txt"],
            key="epic_ticket_example_file",
        )
        ticket_example_text = st.text_area(
            "Ticket example text",
            height=150,
            key="epic_ticket_example_text",
        )
        epic_example_file = st.file_uploader(
            "Epic example (.md/.txt)",
            type=["md", "txt"],
            key="epic_epic_example_file",
        )
        epic_example_text = st.text_area(
            "Epic example text",
            height=150,
            key="epic_epic_example_text",
        )

    parse_button_col, refine_button_col = st.columns(2)
    with parse_button_col:
        parse_clicked = st.button(
            "Parse & Validate",
            use_container_width=True,
            type="secondary",
        )
    with refine_button_col:
        refine_clicked = st.button(
            "Refine Epic Pack",
            use_container_width=True,
            type="primary",
            disabled=state["parse_result"] is None,
        )

    column_overrides = {
        key: value.strip()
        for key, value in {
            "issue_key": issue_key_col,
            "issue_type": issue_type_col,
            "summary": summary_col,
            "description": description_col,
            "parent_key": parent_col,
        }.items()
        if value.strip()
    }

    if parse_clicked:
        if not uploaded_file:
            st.error("Please upload a CSV file to parse.")
        else:
            file_bytes = uploaded_file.getvalue()
            try:
                parse_result = parse_epic_csv(
                    file_content=file_bytes,
                    column_overrides=column_overrides or None,
                )
            except EpicValidationError as exc:
                st.error(f"Validation error: {exc}")
                state["parse_result"] = None
                state["file_bytes"] = None
            else:
                state["file_bytes"] = file_bytes
                state["column_overrides"] = column_overrides
                state["parse_result"] = parse_result
                state["parse_summary"] = {
                    "epic_key": parse_result.epic.key,
                    "children_count": len(parse_result.children),
                    "warnings": list(parse_result.warnings),
                    "excluded": [
                        {
                            "row": row.row_number,
                            "key": row.key,
                            "type": row.issue_type,
                            "reason": row.reason,
                        }
                        for row in parse_result.excluded_rows
                    ],
                    "detected_columns": parse_result.detected_columns,
                }
                state["result"] = None
                state["logs"] = []
                st.success(
                    f"Found epic {parse_result.epic.key} with "
                    f"{len(parse_result.children)} valid child tickets."
                )

    if state["parse_result"]:
        parse_summary = state["parse_summary"]
        st.divider()
        st.subheader("Parse summary")
        cols = st.columns(3)
        cols[0].metric("Epic key", parse_summary.get("epic_key", "—"))
        cols[1].metric("Valid children", parse_summary.get("children_count", 0))
        cols[2].metric("Excluded rows", len(parse_summary.get("excluded", [])))

        with st.expander("Detected columns"):
            detected = parse_summary.get("detected_columns", {})
            formatted = "\n".join(
                f"- **{key.replace('_', ' ').title()}**: {value or 'Not found'}"
                for key, value in detected.items()
            )
            st.markdown(formatted or "_No columns detected._")

        if parse_summary.get("warnings"):
            with st.expander("Warnings"):
                st.markdown("\n".join(f"- {warning}" for warning in parse_summary["warnings"]))

        if parse_summary.get("excluded"):
            with st.expander("Excluded rows"):
                st.markdown(
                    "\n".join(
                        f"- Row {row['row']}: {row['key'] or '(no key)'} "
                        f"({row['type'] or 'Unknown'}) – {row['reason']}"
                        for row in parse_summary["excluded"]
                    )
                )

    if refine_clicked:
        if not api_key:
            st.error("OPENAI_API_KEY not set. Cannot refine the epic pack.")
        elif not state["file_bytes"] or not state["parse_result"]:
            st.error("Parse the CSV successfully before refining.")
        elif not project_code.strip():
            st.error("Project code is required.")
        else:
            state["ticket_example"] = load_example_from_file_or_text(
                ticket_example_file, ticket_example_text
            )
            state["epic_example"] = load_example_from_file_or_text(
                epic_example_file, epic_example_text
            )

            progress_log = st.container()
            log_placeholder = progress_log.empty()
            logs: List[str] = []

            def _log(message: str) -> None:
                logs.append(message)
                log_placeholder.markdown("\n".join(f"- {entry}" for entry in logs))

            try:
                config = EpicPackConfig(
                    project=project_code.strip(),
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    concurrency=int(concurrency),
                    output_base_dir=output_dir.strip() or "./out/epic_packs",
                    ticket_example=state["ticket_example"],
                    epic_example=state["epic_example"],
                    dry_run=False,
                    prompt_version=(
                        f"{PROMPT_VERSION}-nocache-{int(time.time())}"
                        if force_fresh
                        else PROMPT_VERSION
                    ),
                )
                result = run_epic_pack_pipeline(
                    file_content=state["file_bytes"],
                    column_overrides=state["column_overrides"],
                    config=config,
                    progress_callback=_log,
                    squad=selected_squad,
                )
                state["result"] = result
                state["logs"] = logs
                st.success("Epic pack refinement complete.")
            except Exception as exc:  # pragma: no cover - Streamlit UI
                st.error(f"Failed to refine epic pack: {exc}")
                st.exception(exc)

    if state.get("result"):
        result: EpicPackResult = state["result"]
        if not result.outputs:
            st.warning("No outputs available (dry run?).")
            return

        st.divider()
        st.subheader("Epic Pack Outputs")
        st.markdown(
            f"Artefacts saved under `{result.outputs.output_directory}`. "
            f"Cache hits – tickets: {result.cache_hits.get('tickets', 0)}, "
            f"epic: {result.cache_hits.get('epic', 0)}, "
            f"suggestions: {result.cache_hits.get('suggestions', 0)}, "
            f"gap: {result.cache_hits.get('gap', 0)}."
        )

        tabs = st.tabs(["Epic", "Stories", "Actions", "Suggestions", "Index"])

        with tabs[0]:
            st.markdown(result.outputs.epic_md)
        with tabs[1]:
            st.markdown(result.outputs.stories_md)
        with tabs[2]:
            st.markdown(result.outputs.actions_md)
        with tabs[3]:
            st.markdown(result.outputs.suggestions_md)
        with tabs[4]:
            st.markdown(result.outputs.index_md)

        output_dir = Path(result.outputs.output_directory)
        zip_path = Path(result.outputs.zip_path)
        csv_path = Path(result.outputs.refined_csv)

        downloads_col1, downloads_col2 = st.columns(2)
        with downloads_col1:
            if zip_path.exists():
                st.download_button(
                    "Download pack.zip",
                    data=zip_path.read_bytes(),
                    file_name=zip_path.name,
                    mime="application/zip",
                )
        with downloads_col2:
            if csv_path.exists():
                st.download_button(
                    "Download refined_tickets.csv",
                    data=csv_path.read_bytes(),
                    file_name=csv_path.name,
                    mime="text/csv",
                )

        if state.get("logs"):
            with st.expander("Run log"):
                st.markdown("\n".join(f"- {entry}" for entry in state["logs"]))


def ensure_core_banking_state() -> None:
    if "core_banking_update" not in st.session_state:
        st.session_state.core_banking_update = None
    if "core_banking_editable" not in st.session_state:
        st.session_state.core_banking_editable = ""


def render_core_banking_weekly_tab(config: Dict[str, Any]) -> None:
    """Render the Core Banking Weekly Update workflow."""
    ensure_core_banking_state()

    st.header("🏦 Core Banking Weekly Update")
    st.markdown(
        "Paste freehand notes and generate a structured weekly update suitable for senior stakeholders."
    )

    team_name = st.text_input(
        "Team/Programme name",
        value="Customer and Accounts Team",
        help="Appears as the heading in the output.",
        key="cb_team_name",
    )
    notes = st.text_area(
        "Freehand notes (Markdown or plaintext)",
        height=260,
        placeholder="Type or paste your notes here...",
        key="cb_notes",
    )

    with st.expander("📋 Optional: Example format to match"):
        example_file = st.file_uploader(
            "Upload example (.md/.txt)",
            type=["md", "txt"],
            key="cb_example_file",
        )
        example_text = st.text_area(
            "Or paste example format",
            height=150,
            key="cb_example_text",
        )

    generate = st.button(
        "✨ Generate Weekly Update",
        type="primary",
        use_container_width=True,
        key="cb_generate",
    )

    st.subheader("📝 Output")

    if generate:
        if not notes.strip():
            st.error("Please enter some notes.")
            return
        if not config.get("api_key"):
            st.error("OPENAI_API_KEY not set. Cannot generate the weekly update.")
            return
        example_format = load_example_from_file_or_text(example_file, example_text)
        try:
            with st.spinner("Generating weekly update..."):
                content = generate_core_banking_weekly_update(
                    notes=notes.strip(),
                    team_name=team_name.strip() or "Customer and Accounts Team",
                    model=config["model"],
                    max_tokens=min(1400, config["max_tokens"]),
                    temperature=config["temperature"],
                    example_format=example_format,
                )
            st.success("✓ Update generated")
            st.session_state.core_banking_update = content
            st.session_state.core_banking_editable = content
        except Exception as exc:  # pragma: no cover - Streamlit UI
            st.error(f"Failed to generate weekly update: {exc}")
            st.exception(exc)

    if st.session_state.core_banking_update:
        st.markdown("_You can edit the output below before downloading._")
        st.session_state.core_banking_editable = st.text_area(
            "Editable Weekly Update (Markdown)",
            value=st.session_state.core_banking_editable,
            height=320,
            key="cb_output_edit",
        )
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "⬇️ Download as Markdown",
                data=st.session_state.core_banking_editable,
                file_name="core_banking_weekly_update.md",
                mime="text/markdown",
            )
        with col2:
            st.download_button(
                "⬇️ Download as Text",
                data=st.session_state.core_banking_editable,
                file_name="core_banking_weekly_update.txt",
                mime="text/plain",
            )

def render_bulk_ticket_refiner_tab(config: Dict[str, Any]) -> None:
    st.header("🧩 Bulk Ticket Refiner")
    st.markdown("Upload a CSV of Jira tickets to refine titles/descriptions, audit epics, and suggest fix version groups.")

    if "bulk_state" not in st.session_state:
        st.session_state.bulk_state = {
            "result": None,
            "detected_columns": {},
            "errors": [],
        }
    state = st.session_state.bulk_state

    uploader_col, settings_col = st.columns([2, 1])
    with uploader_col:
        uploaded_file = st.file_uploader(
            "Upload Jira CSV",
            type=["csv"],
            help="Required columns: Issue Key, Summary, Description, Parent Key, Fix Versions",
            key="bulk_csv_file",
        )
        project = st.text_input(
            "Project code",
            placeholder="CPS",
            help="Used in prompts.",
            key="bulk_project_code",
        )
        batch_size = st.number_input(
            "Batch size",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
            help="Number of tickets processed per LLM batch.",
            key="bulk_batch_size",
        )
    with settings_col:
        model = st.selectbox(
            "Model",
            MODEL_OPTIONS,
            index=0,
            key="bulk_model",
        )
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=0.2,
            step=0.1,
            key="bulk_temperature",
        )
        max_tokens = st.number_input(
            "Max tokens",
            min_value=600,
            max_value=4000,
            value=1600,
            step=100,
            key="bulk_max_tokens",
        )

    run = st.button(
        "Run Refinement",
        type="primary",
        use_container_width=True,
        key="bulk_run_button",
    )

    if run:
        if not uploaded_file:
            st.error("Please upload a CSV file.")
            return
        if not project.strip():
            st.error("Project code is required.")
            return
        if not config.get("api_key"):
            st.error("OPENAI_API_KEY not set. Cannot run refinement.")
            return

        file_bytes = uploaded_file.getvalue()

        progress_area = st.container()
        progress_placeholder = progress_area.empty()

        def _log(msg: str) -> None:
            progress_placeholder.markdown(f"- {msg}")

        try:
            result, detected, errors = run_bulk_refiner_pipeline(
                file_bytes=file_bytes,
                config=BulkRefinerConfig(
                    project=project.strip(),
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    batch_size=int(batch_size),
                ),
                progress=_log,
            )
            state["result"] = result
            state["detected_columns"] = detected
            state["errors"] = errors
            st.success("✓ Refinement complete")
        except Exception as exc:  # pragma: no cover - Streamlit UI
            st.error(f"Failed to run bulk refinement: {exc}")
            st.exception(exc)

    if state.get("result"):
        result = state["result"]
        st.divider()
        st.subheader("Results")

        cols = st.columns(3)
        cols[0].metric("Tickets refined", len(result.refined))
        cols[1].metric("Missing Epic %", f"{result.epic_audit.percent_missing_epic:.1f}%")
        cols[2].metric("Suggested groups", len(result.fix_versions.groups))

        if state.get("errors"):
            with st.expander("Warnings / Errors"):
                st.markdown(
                    "\n".join(f"- {msg}" for msg in state.get("errors", []))
                    or "_No errors recorded._"
                )

        tickets_tab, epic_tab, fix_tab, downloads_tab = st.tabs(
            ["Refined Tickets", "Epic Audit", "Fix Version Groups", "Downloads"]
        )

        with tickets_tab:
            for t in result.refined:
                with st.expander(f"{t.issue_key} — {t.refined_summary}"):
                    st.markdown(t.refined_description or "_No description_")
                    st.markdown("**Acceptance Criteria**")
                    if t.acceptance_criteria:
                        st.markdown("\n".join(f"- {ac}" for ac in t.acceptance_criteria))
                    else:
                        st.markdown("- Not enough information provided")

        with epic_tab:
            st.markdown(epic_audit_to_markdown(result))

        with fix_tab:
            st.markdown(fix_versions_to_markdown(result))

        with downloads_tab:
            st.download_button(
                "Download refined tickets (CSV)",
                data=refined_tickets_to_csv(result.refined),
                file_name="refined_tickets.csv",
                mime="text/csv",
            )
            st.download_button(
                "Download refined tickets (Markdown)",
                data=refined_tickets_to_markdown(result.refined),
                file_name="refined_tickets.md",
                mime="text/markdown",
            )
            st.download_button(
                "Download epic audit (Markdown)",
                data=epic_audit_to_markdown(result),
                file_name="epic_audit.md",
                mime="text/markdown",
            )
            st.download_button(
                "Download fix version recommendations (Markdown)",
                data=fix_versions_to_markdown(result),
                file_name="fix_version_recommendations.md",
                mime="text/markdown",
            )
def main() -> None:
    """Main Streamlit app."""
    st.set_page_config(
        page_title="Release Notes Generator",
        page_icon="📝",
        layout="wide",
    )

    st.title("📝 Release Notes Generator")
    st.markdown("Generate release artefacts or refine epic packs in Streamlit.")

    sidebar_config = configure_release_sidebar()

    release_tab, epic_tab, bulk_tab, core_banking_tab = st.tabs(
        ["Release Notes", "Epic Pack Refiner", "Bulk Ticket Refiner", "Core Banking Weekly Update"]
    )
    with release_tab:
        render_release_notes_tab(sidebar_config)
    with epic_tab:
        render_epic_pack_tab(sidebar_config["api_key"])
    with bulk_tab:
        render_bulk_ticket_refiner_tab(sidebar_config)
    with core_banking_tab:
        render_core_banking_weekly_tab(sidebar_config)


if __name__ == "__main__":
    main()

