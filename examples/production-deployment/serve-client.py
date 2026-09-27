#!/usr/bin/env python3
"""Runnable wrapper for the maintained PromptVault Serve API client."""

import runpy
from pathlib import Path

runpy.run_path(
    Path(__file__).resolve().parents[2] / "scripts" / "serve-client.py",
    run_name="__main__",
)
