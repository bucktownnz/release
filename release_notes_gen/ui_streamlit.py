"""Streamlit web interface for release notes generator."""

import os
import tempfile
import time
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

from .csv_loader import load_csv
from .llm import (
    generate_fix_version_notes,
    generate_confluence_notes,
    generate_slack_announcement,
)
from .writer import write_outputs


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
                return content.decode("utf-8").strip()
            return str(content).strip()
        except Exception as e:
            st.error(f"Error reading uploaded file: {e}")
            return None
    
    if text_area and text_area.strip():
        return text_area.strip()
    
    return None


def main():
    """Main Streamlit app."""
    st.set_page_config(
        page_title="Release Notes Generator",
        page_icon="📝",
        layout="wide",
    )
    
    st.title("📝 Release Notes Generator")
    st.markdown("Generate release notes from Jira CSV exports using OpenAI")
    
    # Initialize session state
    if "results" not in st.session_state:
        st.session_state.results = None
    if "runtime_info" not in st.session_state:
        st.session_state.runtime_info = None
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # API Key check
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            st.error(
                "⚠️ OPENAI_API_KEY not set. "
                "Set it in your environment or create a .env file."
            )
        else:
            st.success("✓ API key loaded")
        
        st.divider()
        
        # Model selection
        model = st.selectbox(
            "Model",
            ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            index=0,
        )
        
        # Advanced options
        with st.expander("🔧 Advanced Options"):
            max_tokens = st.number_input(
                "Max Tokens",
                min_value=100,
                max_value=8000,
                value=2000,
                step=100,
            )
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=0.2,
                step=0.1,
            )
            limit = st.number_input(
                "Limit Tickets",
                min_value=0,
                value=0,
                help="0 = process all tickets",
            )
            
            st.subheader("Column Overrides")
            summary_col_override = st.text_input(
                "Summary Column",
                help="Leave empty for auto-detection",
            )
            description_col_override = st.text_input(
                "Description Column",
                help="Leave empty for auto-detection",
            )
            key_col_override = st.text_input(
                "Key Column",
                help="Leave empty for auto-detection",
            )
    
    # Main content area
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📤 Input")
        
        # CSV upload
        uploaded_file = st.file_uploader(
            "Upload Jira CSV",
            type=["csv"],
            help="Upload a CSV file exported from Jira",
        )
        
        # Project and version inputs
        fix_version = st.text_input(
            "Fix Version *",
            placeholder="v1.2.3",
            help="Required: The fix version string",
        )
        project = st.text_input(
            "Project Code",
            placeholder="CPS",
            help="Optional: Project code/name",
        )
        
        # Examples section
        with st.expander("📋 Example Formats (Optional)"):
            st.markdown(
                "Provide example formats to guide the model. "
                "Uploaded files take precedence over text areas."
            )
            
            st.subheader("Jira Fix Version Notes")
            fix_notes_file = st.file_uploader(
                "Upload example (.md/.txt)",
                type=["md", "txt"],
                key="fix_notes_file",
            )
            fix_notes_text = st.text_area(
                "Or paste example format",
                height=150,
                key="fix_notes_text",
                help="Markdown format",
            )
            
            st.subheader("Confluence Notes")
            confluence_file = st.file_uploader(
                "Upload example (.md/.txt)",
                type=["md", "txt"],
                key="confluence_file",
            )
            confluence_text = st.text_area(
                "Or paste example format",
                height=150,
                key="confluence_text",
                help="Markdown format",
            )
            
            st.subheader("Slack/Teams Announcement")
            slack_file = st.file_uploader(
                "Upload example (.md/.txt)",
                type=["md", "txt"],
                key="slack_file",
            )
            slack_text = st.text_area(
                "Or paste example format",
                height=150,
                key="slack_text",
                help="Plain text format",
            )
        
        # Generate button
        generate_button = st.button(
            "🚀 Generate Release Notes",
            type="primary",
            use_container_width=True,
        )
    
    with col2:
        st.header("📥 Output")
        
        if generate_button:
            # Validate inputs
            if not uploaded_file:
                st.error("Please upload a CSV file")
                st.stop()
            
            if not fix_version:
                st.error("Please enter a Fix Version")
                st.stop()
            
            if not api_key:
                st.error("OPENAI_API_KEY not set. Cannot generate notes.")
                st.stop()
            
            # Save CSV to temp file
            with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".csv") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name
            
            try:
                # Load CSV
                with st.spinner("Loading CSV..."):
                    try:
                        tickets, detected_columns = load_csv(
                            file_path=tmp_path,
                            summary_col=summary_col_override if summary_col_override else None,
                            description_col=description_col_override if description_col_override else None,
                            key_col=key_col_override if key_col_override else None,
                            limit=limit if limit > 0 else 0,
                        )
                        
                        st.success(f"✓ Loaded {len(tickets)} tickets")
                        st.info(
                            f"Detected columns: "
                            f"Summary='{detected_columns['summary']}', "
                            f"Description='{detected_columns['description']}', "
                            f"Key='{detected_columns['key'] or 'N/A'}'"
                        )
                    except Exception as e:
                        st.error(f"Error loading CSV: {e}")
                        st.stop()
                
                # Extract examples
                fix_notes_example = load_example_from_file_or_text(
                    fix_notes_file, fix_notes_text
                )
                confluence_example = load_example_from_file_or_text(
                    confluence_file, confluence_text
                )
                slack_example = load_example_from_file_or_text(
                    slack_file, slack_text
                )
                
                # Generate notes
                start_time = time.time()
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                try:
                    # Jira Fix Version notes
                    status_text.text("Generating Jira Fix Version notes...")
                    progress_bar.progress(33)
                    fix_version_content = generate_fix_version_notes(
                        tickets,
                        project or "Project",
                        fix_version,
                        model,
                        max_tokens,
                        temperature,
                        fix_notes_example,
                    )
                    
                    # Confluence notes
                    status_text.text("Generating Confluence notes...")
                    progress_bar.progress(66)
                    confluence_content = generate_confluence_notes(
                        tickets,
                        project or "Project",
                        fix_version,
                        model,
                        max_tokens,
                        temperature,
                        confluence_example,
                    )
                    
                    # Slack announcement
                    status_text.text("Generating Slack announcement...")
                    progress_bar.progress(100)
                    slack_content = generate_slack_announcement(
                        tickets,
                        project or "Project",
                        fix_version,
                        model,
                        max_tokens,
                        temperature,
                        slack_example,
                    )
                    
                    elapsed_time = time.time() - start_time
                    progress_bar.empty()
                    status_text.empty()
                    
                    # Save to output directory
                    out_dir = "./out"
                    fix_version_path, confluence_path, slack_path = write_outputs(
                        out_dir,
                        fix_version_content,
                        confluence_content,
                        slack_content,
                    )
                    
                    # Store results in session state
                    st.session_state.results = {
                        "fix_version": fix_version_content,
                        "confluence": confluence_content,
                        "slack": slack_content,
                    }
                    st.session_state.runtime_info = {
                        "tickets_processed": len(tickets),
                        "elapsed_time": elapsed_time,
                    }
                    
                    st.success("✓ Generation complete!")
                    
                except Exception as e:
                    st.error(f"Error generating notes: {e}")
                    st.exception(e)
            
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except:
                    pass
        
        # Display results
        if st.session_state.results:
            runtime_info = st.session_state.runtime_info or {}
            
            st.info(
                f"Processed {runtime_info.get('tickets_processed', 0)} tickets "
                f"in {runtime_info.get('elapsed_time', 0):.2f}s"
            )
            
            # Tabs for different outputs
            tab1, tab2, tab3 = st.tabs(
                ["Jira Notes", "Confluence Notes", "Slack Announcement"]
            )
            
            with tab1:
                st.subheader("Jira Fix Version Notes")
                st.markdown(st.session_state.results["fix_version"])
                st.download_button(
                    "Download",
                    data=st.session_state.results["fix_version"],
                    file_name="jira_fix_version_notes.md",
                    mime="text/markdown",
                )
            
            with tab2:
                st.subheader("Confluence Release Notes")
                st.markdown(st.session_state.results["confluence"])
                st.download_button(
                    "Download",
                    data=st.session_state.results["confluence"],
                    file_name="confluence_release_notes.md",
                    mime="text/markdown",
                )
            
            with tab3:
                st.subheader("Slack/Teams Announcement")
                st.text(st.session_state.results["slack"])
                st.download_button(
                    "Download",
                    data=st.session_state.results["slack"],
                    file_name="slack_announcement.txt",
                    mime="text/plain",
                )


if __name__ == "__main__":
    main()

