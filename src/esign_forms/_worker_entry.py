"""``esign-forms-worker`` console script; fails cleanly when the ``worker`` extra is missing."""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from esign_forms.temporal.worker import main as worker_main
    except ImportError as e:
        print(f"esign-forms-worker: {e}", file=sys.stderr)
        sys.exit(1)
    worker_main()
