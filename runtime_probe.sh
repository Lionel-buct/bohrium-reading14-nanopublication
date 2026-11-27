#!/usr/bin/env bash
set -eu

SKILL_DIR="${SKILL_DIR:-/skills/weekly-skill}"
PYTHON_BIN="$(command -v python3 || command -v python)"
exec "$PYTHON_BIN" "$SKILL_DIR/scripts/runtime_probe.py" "$@"
