#!/usr/bin/env python3
"""Compatibility entrypoint for the representative performance dataset."""

import runpy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "simulate-traffic.py"

if __name__ == "__main__":
    runpy.run_path(str(SCRIPT), run_name="__main__")
