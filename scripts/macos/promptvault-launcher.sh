#!/bin/zsh
set -eu

# Finder does not inherit the PATH from an interactive terminal.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"
SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h}"
cd "${PROJECT_ROOT}"
exec "${PROJECT_ROOT}/.venv/bin/python" "${SCRIPT_DIR}/launch.py"
