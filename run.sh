#!/bin/bash
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt -q

echo "Starting WC 2026 Fantasy Optimizer at http://localhost:8001"
uvicorn main:app --reload --port 8001
