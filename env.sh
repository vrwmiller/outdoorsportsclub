#!/usr/bin/env bash
# env.sh — one-time dev environment setup
# Usage: source env.sh
#
# Must be sourced (not run as a subshell) so that .venv activation
# propagates to your current shell session.
set -euo pipefail

PYTHON=${PYTHON:-python3.13}

if [ ! -d .venv ]; then
  echo "Creating .venv with $PYTHON..."
  "$PYTHON" -m venv .venv
else
  echo ".venv already exists, skipping creation."
fi

echo "Installing dev dependencies..."
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements-dev.txt --quiet

echo ""
# shellcheck source=.venv/bin/activate
source .venv/bin/activate
echo "Done. .venv activated. Run 'deactivate' when finished."
