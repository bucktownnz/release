# Release Notes Generator

Generate professional release notes from Jira CSV exports using OpenAI. Supports both command-line and web interfaces.

## Features

- 📊 Flexible CSV parsing with automatic column detection
- 🤖 OpenAI-powered content generation
- 📝 Three output formats:
  - Jira Fix Version release notes
  - Confluence-ready business-value notes
  - Slack/Teams announcements
- 🧭 Epic Pack Refiner for epic-level planning (Streamlit tab + CLI subcommand)
- 🎨 Custom example formats to guide output structure
- 🔄 Automatic retry with exponential backoff
- 💻 CLI and Streamlit web UI

## Installation

### Prerequisites

- Python 3.11 or higher
- OpenAI API key

### Setup

1. Clone or navigate to the project directory:
```bash
cd release_notes_gen
```

2. Install dependencies:
```bash
# Using uv (recommended)
uv pip install -e .

# Or using pip
pip install -e .
```

3. Set up your OpenAI API key:

Create a `.env` file in the project root:
```env
OPENAI_API_KEY=sk-...
```

Or export it in your shell:
```bash
export OPENAI_API_KEY="sk-..."
```

## Usage

### Command-Line Interface

#### Basic Usage

```bash
python -m release_notes_gen \
  --input ./data/release.csv \
  --fix-version "v1.2.3" \
  --project "CPS"
```

#### With Example Formats

```bash
python -m release_notes_gen \
  --input ./data/release.csv \
  --fix-version "v1.2.3" \
  --project "CPS" \
  --fix-notes-example ./examples/jira_example.md \
  --confluence-example ./examples/confluence_example.md \
  --slack-example ./examples/slack_example.txt
```

#### Advanced Options

```bash
python -m release_notes_gen \
  --input ./data/release.csv \
  --fix-version "v1.2.3" \
  --project "CPS" \
  --model "gpt-4o" \
  --max-tokens 3000 \
  --temperature 0.3 \
  --limit 50 \
  --out-dir ./custom_output \
  --summary-col "Issue Summary" \
  --description-col "Issue Description"
```

#### Dry Run

Test CSV parsing without generating notes:

```bash
python -m release_notes_gen \
  --input ./data/release.csv \
  --fix-version "v1.2.3" \
  --dry-run
```

#### Epic Pack Refiner

Refine an epic and its child tickets into a complete artefact pack:

```bash
python -m release_notes_gen epic-refiner \
  --input ./data/epic.csv \
  --project CPS \
  --model gpt-4o-mini \
  --temperature 0 \
  --max-tokens 1800 \
  --concurrency 4 \
  --out-dir ./out/epic_packs \
  --ticket-example ./examples/ticket_example.md \
  --epic-example ./examples/epic_example.md \
  --summary-col Summary \
  --description-col Description \
  --parent-col "Parent key"
```

Add `--dry-run` to validate the CSV without invoking the OpenAI API.

### Web Interface (Streamlit)

Launch the web UI:

```bash
streamlit run release_notes_gen/ui_streamlit.py
```

Then open http://localhost:8501 in your browser.

**Features:**
- Switch between Release Notes and Epic Pack Refiner tabs
- Upload CSV files via drag-and-drop
- Configure model and parameters for each workflow
- Provide example formats via file upload or text paste
- Preview and download generated notes
- Session state caching to avoid recomputation

## CSV Format

The tool automatically detects columns with flexible matching:

- **Summary**: `summary`, `issue summary`, `title`
- **Description**: `description`, `issue description`, `details`
- **Key**: `key`, `issue key` (optional)

Column names are matched case-insensitively. You can override column names using CLI flags or the web UI.

### Example CSV

```csv
Key,Summary,Description
CPS-123,Fix login bug,Users unable to log in with special characters
CPS-124,Add dark mode,New dark theme for better UX
```

## Output Files

All outputs are written to the `out/` directory (or custom `--out-dir`):

- `jira_fix_version_notes.md` - Jira Fix Version release notes
- `confluence_release_notes.md` - Confluence-ready notes
- `slack_announcement.txt` - Slack/Teams announcement

Epic Pack Refiner runs create a timestamped folder under `out/epic_packs/`:

- `epic.md` – refined epic narrative
- `stories.md` – refined child tickets
- `actions.md` – aggregated questions and gaps
- `suggested_new_tickets.md` – higher-value slices and missing work
- `index.md` – run summary, warnings, and traceability footer
- `refined_tickets.csv` – quick reference of refined titles/summaries
- `pack.zip` – ready-to-share archive of the artefacts

## Example Formats

You can provide example formats to guide the model's output structure. Examples can be:

- Uploaded as files (`.md` or `.txt`)
- Pasted into text areas (web UI)
- Specified via CLI flags (e.g., `--fix-notes-example`)

When an example is provided, the model will match its structure and headings exactly.

See the `examples/` directory for sample formats.

## CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--input` | Path to Jira CSV file | Required |
| `--fix-version` | Fix version string | Required |
| `--project` | Project code/name | "" |
| `--summary-col` | Override summary column name | Auto-detect |
| `--description-col` | Override description column name | Auto-detect |
| `--key-col` | Override key column name | Auto-detect |
| `--model` | OpenAI model to use | `gpt-4o-mini` |
| `--max-tokens` | Maximum tokens for response | 2000 |
| `--temperature` | Temperature for generation | 0.2 |
| `--limit` | Limit number of tickets (0 = all) | 0 |
| `--out-dir` | Output directory | `./out` |
| `--dry-run` | Parse CSV and exit | False |
| `--fix-notes-example` | Example file for Jira notes | None |
| `--confluence-example` | Example file for Confluence | None |
| `--slack-example` | Example file for Slack | None |

## Error Handling

- **Missing API Key**: Clear error message with setup instructions
- **CSV Parsing Errors**: Detailed messages about missing columns
- **API Errors**: Automatic retry with exponential backoff (up to 5 attempts)
- **File Errors**: Graceful handling with informative messages

## Project Structure

```
release_notes_gen/
├── __init__.py
├── __main__.py            # CLI entrypoint
├── csv_loader.py          # CSV parsing + header detection
├── llm.py                 # OpenAI API calls + retry/backoff
├── prompts.py             # Prompt templates
├── writer.py              # File output helpers
└── ui_streamlit.py        # Streamlit web app

examples/
├── jira_example.md
├── confluence_example.md
└── slack_example.txt

pyproject.toml
README.md
```

## Development

### Running Tests

```bash
# Dry run to test CSV parsing
python -m release_notes_gen --input test.csv --fix-version "v1.0.0" --dry-run
```

### Dependencies

- `openai>=1.0.0` - OpenAI API client
- `streamlit>=1.28.0` - Web UI framework
- `python-dotenv>=1.0.0` - Environment variable loading
- `tenacity>=8.2.0` - Retry logic
- `rich>=13.0.0` - Enhanced CLI output (optional)

## License

MIT

## Contributing

Contributions welcome! Please open an issue or pull request.

