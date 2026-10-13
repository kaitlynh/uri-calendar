#!/bin/bash
set -e

VENV_DIR="$(dirname "$0")/.venv"
REQUIREMENTS="$(dirname "$0")/../requirements.txt"
STAMP="$VENV_DIR/.requirements-installed"

# Create venv on first run
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Install dependencies on first run and whenever requirements.txt changed since.
# A failed install (e.g. offline) is a warning, not a stop.
if [ ! -f "$STAMP" ] || [ "$REQUIREMENTS" -nt "$STAMP" ]; then
    echo "Installing dependencies..."
    if "$VENV_DIR/bin/pip" install --quiet -r "$REQUIREMENTS"; then
        touch "$STAMP"
    else
        echo "WARNING: dependency install failed, continuing with what is installed"
    fi
fi

# Run from the project root so sources.json path resolves correctly
cd "$(dirname "$0")/.."

# scraping.py must finish before ai.py (ai.py merges into events.json)
"$VENV_DIR/bin/python" scraping/scraping.py

# AI enrichment is optional — don't stop the pipeline if it fails
"$VENV_DIR/bin/python" scraping/open-ai.py || echo "WARNING: AI enrichment failed (non-fatal)"

# Ingest into database
"$VENV_DIR/bin/python" db/parse_json.py

# Validate pipeline results
"$VENV_DIR/bin/python" tests/validate_pipeline.py
