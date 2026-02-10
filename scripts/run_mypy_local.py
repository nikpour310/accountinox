#!/usr/bin/env python3
"""Run mypy programmatically to avoid shell quoting issues on Windows."""
from __future__ import annotations
import sys
from mypy import api

args = [
    "--show-error-codes",
    "--explicit-package-bases",
    "apps:./apps,core:./core",
    "--exclude",
    "apps/blog/extractor.py",
    "apps",
]

stdout, stderr, exit_code = api.run(args)
if stdout:
    print(stdout, end="")
if stderr:
    print(stderr, file=sys.stderr, end="")
sys.exit(exit_code)
