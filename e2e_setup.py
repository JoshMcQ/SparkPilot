#!/usr/bin/env python
"""Compatibility wrapper for the canonical BYOC-lite live smoke runner.

This entrypoint is intentionally thin so older docs/notes still work.
Use `scripts/smoke/live_byoc_lite.py` directly for new automation.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def main() -> int:
    script = Path(__file__).resolve().parent / "scripts" / "smoke" / "live_byoc_lite.py"
    if not script.exists():
        print(f"Missing smoke runner: {script}", file=sys.stderr)
        return 2
    print(
        "WARNING: e2e_setup.py is deprecated. "
        "Forwarding to scripts/smoke/live_byoc_lite.py.",
        file=sys.stderr,
    )
    command = [sys.executable, str(script), *sys.argv[1:]]
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
