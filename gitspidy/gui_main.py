"""Standalone entry point for the GitSpidy graphical application."""

from __future__ import annotations

import sys

from gitspidy.gui import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
