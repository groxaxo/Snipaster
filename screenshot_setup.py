#!/usr/bin/env python3
"""Plain, dependency-light entry point for installing Snipaster."""

from __future__ import annotations

import sys

from snipaster_installer import InstallError, install, prepare_privileges


def main() -> int:
    print("Installing Snipaster desktop capture and annotation tools...")
    try:
        prepare_privileges()
        result = install(progress=lambda message: print(f"• {message}"))
    except InstallError as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        return 1

    print("\nSnipaster is ready.")
    print("Press F1, click the desktop icon, or use the tray capture icon.")
    print(f"Hotkey: {result.hotkey}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
