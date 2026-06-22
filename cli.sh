#!/usr/bin/env bash
#
# cli.sh — launch the zkzkAgent interactive chat CLI.
#
# Usage:
#   ./cli.sh                 normal
#   ./cli.sh --verbose       show the agent's internal INFO logs
#   ./cli.sh --debug         show everything (DEBUG)
#   ./cli.sh --user alice    override the dummy user id
#
set -euo pipefail

# Resolve the project root (directory of this script) so it works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Prefer a local virtualenv if present, otherwise fall back to python3.
if [[ -x ".venv/bin/python" ]]; then
    PY=".venv/bin/python"
elif [[ -x "venv/bin/python" ]]; then
    PY="venv/bin/python"
else
    PY="$(command -v python3 || command -v python)"
fi

if [[ -z "${PY:-}" ]]; then
    echo "error: no python interpreter found on PATH" >&2
    exit 1
fi

exec "$PY" -m chat_cli "$@"
