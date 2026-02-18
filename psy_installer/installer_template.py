#!/usr/bin/env python3
import threading
import time
import subprocess
import os
import sys
from asciimatics.effects import Print, Cycle, Stars, Effect
from asciimatics.renderers import Plasma, FigletText, Rainbow
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.exceptions import ResizeScreenError, StopApplication
from asciimatics.event import KeyboardEvent

# --- CONFIGURATION ---
INSTALL_NAME = "MY PROJECT"
INSTALL_SUCCESS = False
INSTALL_MESSAGE = "Initializing..."


def check_and_install(package, command_name=None):
    """Check if a package is installed, and install it if not."""
    cmd_to_check = command_name if command_name else package
    check_cmd = f"which {cmd_to_check}"

    install_cmd = f"sudo apt install -y {package}"

    # Check if installed
    if (
        subprocess.run(
            check_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode
        != 0
    ):
        subprocess.run(
            f"sudo apt update && {install_cmd}",
            shell=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def run_installation():
    """Run the actual installation commands."""
    global INSTALL_SUCCESS, INSTALL_MESSAGE
    try:
        # TODO: Add your installation steps here
        INSTALL_MESSAGE = "Checking dependencies..."
        time.sleep(1.0)  # Simulate work

        # Example: Install a package
        # INSTALL_MESSAGE = "Installing curl..."
        # check_and_install("curl")

        # Example: Run a command
        # subprocess.run("npm install", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        INSTALL_MESSAGE = "Configuring system..."
        time.sleep(1.5)  # Simulate work

        INSTALL_MESSAGE = "Finalizing setup..."
        time.sleep(1.0)  # Simulate work

        INSTALL_SUCCESS = True

    except Exception as e:
        INSTALL_MESSAGE = f"Error: {e}"
        # Wait for user to see error
        time.sleep(5)
        INSTALL_SUCCESS = True  # Exit anyway (or handle differently)


class CheckInstallStatus(Effect):
    """Effect to check if installation is complete."""

    def __init__(self, screen, **kwargs):
        super(CheckInstallStatus, self).__init__(screen, **kwargs)

    def _update(self, frame_no):
        if INSTALL_SUCCESS:
            raise StopApplication("Install Complete")

    @property
    def stop_frame(self):
        return 0

    def process_event(self, event):
        # Allow quitting with 'q'
        if isinstance(event, KeyboardEvent):
            if event.key_code == ord("q") or event.key_code == ord("Q"):
                raise StopApplication("User Cancelled")
        return event

    def reset(self):
        pass


class StatusText(Effect):
    """Effect to display the current installation status."""

    def __init__(self, screen, **kwargs):
        super(StatusText, self).__init__(screen, **kwargs)

    def _update(self, frame_no):
        # Center the text
        msg = f" {INSTALL_MESSAGE} "
        x = max(0, (self._screen.width - len(msg)) // 2)
        y = (self._screen.height // 2) + 6

        # Clear line area first (simple clear)
        self._screen.print_at(" " * self._screen.width, 0, y, bg=Screen.COLOUR_BLACK)
        self._screen.print_at(
            msg, x, y, colour=Screen.COLOUR_CYAN, bg=Screen.COLOUR_BLACK
        )

        # Loading bar
        bar_width = min(40, self._screen.width - 4)
        if bar_width > 0:
            filled_len = (frame_no % bar_width) + 1
            # "Ping pong" effect for bar
            cycle = frame_no % (bar_width * 2)
            if cycle > bar_width:
                filled_len = bar_width - (cycle - bar_width)
            else:
                filled_len = cycle

            bar_content = "=" * filled_len + " " * (bar_width - filled_len)
            bar = f"[{bar_content}]"
            bx = max(0, (self._screen.width - len(bar)) // 2)
            by = y + 2

            self._screen.print_at(
                " " * self._screen.width, 0, by, bg=Screen.COLOUR_BLACK
            )
            self._screen.print_at(
                bar, bx, by, colour=Screen.COLOUR_GREEN, bg=Screen.COLOUR_BLACK
            )

    @property
    def stop_frame(self):
        return 0

    def reset(self):
        pass


def demo(screen):
    """The main animation setup."""

    # Create renderers first to calculate dimensions
    title_renderer = FigletText(INSTALL_NAME, font="big")
    rainbow_title = Rainbow(screen, title_renderer)

    # Calculate centered position
    title_x = max(0, (screen.width - title_renderer.max_width) // 2)

    effects = [
        # 1. Background: Plasma
        Print(
            screen,
            Plasma(screen.height, screen.width, screen.colours),
            0,
            speed=1,
            transparent=False,
        ),
        # 2. Title: Rainbow Figlet
        Print(
            screen,
            rainbow_title,
            y=(screen.height // 2) - 6,
            x=title_x,
            speed=1,
            transparent=True,
        ),
        # 3. Custom Status Text & Progress Bar
        StatusText(screen),
        # 4. Completion Checker
        CheckInstallStatus(screen),
    ]

    screen.play([Scene(effects, -1)], stop_on_resize=True, repeat=False)


def main():
    # Ensure sudo permissions before starting UI if needed
    try:
        subprocess.run(["sudo", "-v"], check=True)
    except subprocess.CalledProcessError:
        print("Sudo permission required for installation.")
        sys.exit(1)

    # Start installation in background
    t = threading.Thread(target=run_installation)
    t.start()

    try:
        Screen.wrapper(demo)
    except ResizeScreenError:
        pass
    except Exception as e:
        print(f"Display error: {e}")

    # Ensure thread joins
    if t.is_alive():
        print("Waiting for installation to finish...")
        while t.is_alive():
            time.sleep(0.5)
        t.join()

    if not INSTALL_SUCCESS:
        print(f"\nInstallation failed: {INSTALL_MESSAGE}")
        sys.exit(1)

    # Final clear and message
    print("\033[H\033[J", end="")  # Clear screen
    print(f"✨ {INSTALL_NAME} SETUP COMPLETE! ✨")


if __name__ == "__main__":
    main()
