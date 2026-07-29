#!/usr/bin/env python3
"""Animated Snipaster installer. Run with: uv run install_snipaster.py"""

from __future__ import annotations

import sys
import threading
import time
from typing import Optional

from asciimatics.effects import Effect, Print
from asciimatics.exceptions import ResizeScreenError, StopApplication
from asciimatics.renderers import FigletText, Plasma, Rainbow
from asciimatics.scene import Scene
from asciimatics.screen import Screen

from snipaster_installer import InstallError, InstallationResult, install, prepare_privileges

INSTALL_NAME = "SNIPASTER"
INSTALL_DONE = False
INSTALL_SUCCESS = False
INSTALL_MESSAGE = "Preparing installation..."
INSTALL_ERROR: Optional[str] = None
INSTALL_RESULT: Optional[InstallationResult] = None


def set_status(message: str) -> None:
    global INSTALL_MESSAGE
    INSTALL_MESSAGE = message


def run_installation() -> None:
    global INSTALL_DONE, INSTALL_SUCCESS, INSTALL_ERROR, INSTALL_RESULT
    try:
        INSTALL_RESULT = install(progress=set_status)
        INSTALL_SUCCESS = True
    except Exception as exc:  # display a clean error after the animation exits
        INSTALL_ERROR = str(exc)
        INSTALL_SUCCESS = False
        set_status(f"Installation failed: {exc}")
    finally:
        INSTALL_DONE = True


class CompletionWatcher(Effect):
    def _update(self, frame_no: int) -> None:
        del frame_no
        if INSTALL_DONE:
            raise StopApplication("Installation finished")

    @property
    def stop_frame(self) -> int:
        return 0

    def reset(self) -> None:
        pass


class StatusPanel(Effect):
    def _update(self, frame_no: int) -> None:
        width = self._screen.width
        message = f" {INSTALL_MESSAGE} "
        if len(message) > width - 4:
            message = message[: max(1, width - 7)] + "..."
        x = max(0, (width - len(message)) // 2)
        y = min(self._screen.height - 4, (self._screen.height // 2) + 6)
        self._screen.print_at(" " * width, 0, y, bg=Screen.COLOUR_BLACK)
        self._screen.print_at(
            message,
            x,
            y,
            colour=Screen.COLOUR_CYAN,
            bg=Screen.COLOUR_BLACK,
        )

        bar_width = max(8, min(46, width - 6))
        cycle = frame_no % (bar_width * 2)
        filled = cycle if cycle <= bar_width else (bar_width * 2) - cycle
        bar = "[" + "=" * filled + " " * (bar_width - filled) + "]"
        self._screen.print_at(" " * width, 0, y + 2, bg=Screen.COLOUR_BLACK)
        self._screen.print_at(
            bar,
            max(0, (width - len(bar)) // 2),
            y + 2,
            colour=Screen.COLOUR_GREEN,
            bg=Screen.COLOUR_BLACK,
        )

    @property
    def stop_frame(self) -> int:
        return 0

    def reset(self) -> None:
        pass


def animation(screen: Screen) -> None:
    title = FigletText(INSTALL_NAME, font="big")
    effects = [
        Print(
            screen,
            Plasma(screen.height, screen.width, screen.colours),
            0,
            speed=1,
            transparent=False,
        ),
        Print(
            screen,
            Rainbow(screen, title),
            y=max(0, (screen.height // 2) - 7),
            x=max(0, (screen.width - title.max_width) // 2),
            speed=1,
            transparent=True,
        ),
        StatusPanel(screen),
        CompletionWatcher(screen),
    ]
    screen.play([Scene(effects, -1)], stop_on_resize=True, repeat=False)


def run_animation_until_complete() -> None:
    while not INSTALL_DONE:
        try:
            Screen.wrapper(animation)
        except ResizeScreenError:
            continue
        except StopApplication:
            break
        except Exception as exc:
            print(f"Animated display unavailable ({exc}); continuing in text mode.")
            while not INSTALL_DONE:
                print(f"\r{INSTALL_MESSAGE:<78}", end="", flush=True)
                time.sleep(0.25)
            print()
            break


def main() -> int:
    try:
        missing = prepare_privileges()
    except InstallError as exc:
        print(f"Snipaster installation failed: {exc}", file=sys.stderr)
        return 1

    if missing:
        print("Administrator access confirmed. Starting Snipaster setup...")

    worker = threading.Thread(target=run_installation, name="snipaster-installer")
    worker.start()
    run_animation_until_complete()
    worker.join()

    print("\033[H\033[J", end="")
    if not INSTALL_SUCCESS or INSTALL_RESULT is None:
        print("SNIPASTER INSTALLATION FAILED")
        print(INSTALL_ERROR or INSTALL_MESSAGE)
        return 1

    result = INSTALL_RESULT
    print("SNIPASTER IS READY")
    print("• Press F1 to capture a region.")
    print("• Click the Snipaster icon on the desktop or in the app menu.")
    print("• Click the tray capture icon for one-click capture.")
    print("• After capture, draw, add text, select/crop, save, or copy.")
    print(f"• Hotkey: {result.hotkey}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
