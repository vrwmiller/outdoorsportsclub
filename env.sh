#!/usr/bin/env bash
# env.sh — one-time dev environment setup
# Usage: source env.sh
#
# Must be sourced (not run as a subshell) so that .venv activation
# propagates to your current shell session.
set -euo pipefail

PYTHON=${PYTHON:-python3}

# Require >= 3.12 — floor matches the Lambda runtime (see ODQ #30 in docs/design.md)
if ! command -v "$PYTHON" &>/dev/null; then
  echo "Error: interpreter not found: $PYTHON" >&2
  exit 1
fi
is_supported_python=$("$PYTHON" -c 'import sys; print(sys.version_info >= (3, 12))')
if [[ "$is_supported_python" != "True" ]]; then
  echo "Error: Python 3.12 or later required (found $("$PYTHON" --version))" >&2
  exit 1
fi

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
