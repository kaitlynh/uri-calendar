#!/bin/bash
set -e

VENV_DIR="$(dirname "$0")/.venv"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Install dependencies
"$VENV_DIR/bin/pip" install --quiet requests beautifulsoup4 feedparser

# Run from the project root so sources.json path resolves correctly
cd "$(dirname "$0")/.."
"$VENV_DIR/bin/python" scraping/ai.py
