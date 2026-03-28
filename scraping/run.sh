#!/bin/bash
set -e

VENV_DIR="$(dirname "$0")/.venv"

# Create venv and install dependencies only on first run
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet requests beautifulsoup4 feedparser openai python-dotenv
fi

# Run from the project root so sources.json path resolves correctly
cd "$(dirname "$0")/.."

# scraping.py must finish before ai.py (ai.py merges into events.json)
"$VENV_DIR/bin/python" scraping/scraping.py
#"$VENV_DIR/bin/python" scraping/open-ai.py
