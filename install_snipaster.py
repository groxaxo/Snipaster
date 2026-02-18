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
INSTALL_NAME = "SNIPASTER"
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


def create_wrapper_script(script_path):
    """Create the screenshot wrapper script."""
    script_content = """#!/bin/bash
# Snipaster wrapper script

# Generate filename
TIMESTAMP=$(date +%Y-%m-%d-%H-%M-%S)
DIR="$HOME/Pictures/Screenshots"
FILE="$DIR/screenshot-$TIMESTAMP.png"

mkdir -p "$DIR"

# Detect session type and run appropriate screenshot tool
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    if command -v gnome-screenshot >/dev/null; then
        # GNOME Screenshot
        gnome-screenshot -a -f "$FILE"
    elif command -v grim >/dev/null && command -v slurp >/dev/null; then
        # Grim/Slurp fallback
        grim -g "$(slurp)" "$FILE"
    else
        notify-send "Snipaster" "No screenshot tool found (gnome-screenshot or grim)"
        exit 1
    fi
else
    # Fallback to scrot for X11
    if command -v scrot >/dev/null; then
        scrot -s "$FILE"
    else
        notify-send "Snipaster" "scrot not found"
        exit 1
    fi
fi

# Check if file was created (screenshot taken)
if [ -f "$FILE" ]; then
    # Copy to clipboard
    if [ "$XDG_SESSION_TYPE" = "wayland" ] && command -v wl-copy >/dev/null; then
        wl-copy < "$FILE"
    elif command -v xclip >/dev/null; then
        xclip -selection clipboard -t image/png -i "$FILE"
    fi
    
    # Notify user (optional, helpful for confirmation)
    if command -v notify-send >/dev/null; then
        notify-send "Snipaster" "Screenshot saved and copied to clipboard"
    fi
fi
"""
    with open(script_path, "w") as f:
        f.write(script_content)
    os.chmod(script_path, 0o755)


def setup_gnome_keybinding(command, binding, name="Snipaster"):
    """Set up GNOME custom keybinding using gsettings."""
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    key = "custom-keybindings"

    try:
        current = subprocess.check_output(
            ["gsettings", "get", schema, key], text=True
        ).strip()
    except subprocess.CalledProcessError:
        return

    if current == "@as []" or current == "[]":
        bindings = []
    else:
        current = current.strip("[]")
        if not current:
            bindings = []
        else:
            bindings = [b.strip().strip("'") for b in current.split(",")]

    path_base = (
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom"
    )

    idx = 0
    new_path = ""
    while True:
        path = f"{path_base}{idx}/"
        if path not in bindings:
            new_path = path
            break
        idx += 1

    bindings.append(new_path)

    bindings_str = "[" + ", ".join([f"'{b}'" for b in bindings]) + "]"
    subprocess.run(
        f'gsettings set {schema} {key} "{bindings_str}"', shell=True, check=True
    )

    rel_schema = f"{schema}.custom-keybinding:{new_path}"
    subprocess.run(f"gsettings set {rel_schema} name '{name}'", shell=True, check=True)
    subprocess.run(
        f"gsettings set {rel_schema} command '{command}'", shell=True, check=True
    )
    subprocess.run(
        f"gsettings set {rel_schema} binding '{binding}'", shell=True, check=True
    )


def run_installation():
    """Run the actual installation commands."""
    global INSTALL_SUCCESS, INSTALL_MESSAGE
    try:
        INSTALL_MESSAGE = "Checking system packages..."
        packages_map = {
            "scrot": "scrot",
            "xbindkeys": "xbindkeys",
            "xclip": "xclip",
            "gnome-screenshot": "gnome-screenshot",
            "wl-clipboard": "wl-copy",
        }

        # Simulate some steps for effect visibility if too fast
        step_delay = 1.5

        for pkg, cmd in packages_map.items():
            INSTALL_MESSAGE = f"Installing {pkg}..."
            check_and_install(pkg, cmd)
            time.sleep(0.5)

        INSTALL_MESSAGE = "Configuring directories..."
        screenshot_dir = os.path.expanduser("~/Pictures/Screenshots")
        autostart_dir = os.path.expanduser("~/.config/autostart")
        os.makedirs(screenshot_dir, exist_ok=True)
        os.makedirs(autostart_dir, exist_ok=True)
        time.sleep(step_delay)

        INSTALL_MESSAGE = "Creating wrapper script..."
        script_path = os.path.expanduser("~/.local/bin/snipaster_shot")
        os.makedirs(os.path.dirname(script_path), exist_ok=True)
        create_wrapper_script(script_path)
        time.sleep(step_delay)

        INSTALL_MESSAGE = "Detecting session type..."
        session_type = os.environ.get("XDG_SESSION_TYPE", "")
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
        time.sleep(1.0)

        if "wayland" in session_type.lower() and "gnome" in desktop.lower():
            INSTALL_MESSAGE = "Configuring GNOME Wayland..."
            setup_gnome_keybinding(script_path, "F1")

            subprocess.run("killall xbindkeys 2>/dev/null || true", shell=True)

            autostart_file = os.path.join(autostart_dir, "xbindkeys.desktop")
            if os.path.exists(autostart_file):
                os.remove(autostart_file)
        else:
            INSTALL_MESSAGE = "Configuring X11/Other..."
            xbindkeys_config = os.path.expanduser("~/.xbindkeysrc")
            config_content = f"""
# Snipaster keybinding
"{script_path}"
  F1
"""
            with open(xbindkeys_config, "w") as f:
                f.write(config_content)

            autostart_file = os.path.join(autostart_dir, "xbindkeys.desktop")
            autostart_content = """
[Desktop Entry]
Type=Application
Name=xbindkeys
Exec=xbindkeys
Terminal=false
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
            with open(autostart_file, "w") as f:
                f.write(autostart_content)

            subprocess.run(
                "killall xbindkeys 2>/dev/null || true && xbindkeys &", shell=True
            )

        time.sleep(step_delay)
        INSTALL_MESSAGE = "Finalizing setup..."
        time.sleep(1.0)

        INSTALL_SUCCESS = True

    except Exception as e:
        INSTALL_MESSAGE = f"Error: {e}"
        # Wait for user to see error
        time.sleep(5)
        INSTALL_SUCCESS = True  # Exit anyway


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
    # max_width might be 0 if font not loaded? No, pyfiglet usually works.
    title_x = max(0, (screen.width - title_renderer.max_width) // 2)

    effects = [
        # 1. Background: Plasma
        # Use screen.colours to respect terminal capabilities
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
    # Ensure sudo permissions before starting UI
    try:
        # Allow user to see sudo prompt if needed
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
        # Log error to file for debugging
        with open("install_debug.log", "w") as f:
            f.write(f"Display error: {e}\n")
        print(f"Graphic mode failed: {e}. Switching to text mode.")

    # Ensure thread joins
    if t.is_alive():
        print("Waiting for installation to finish...")
        # If graphic mode failed, show status in text mode
        while t.is_alive():
            print(f"\r{INSTALL_MESSAGE}", end="", flush=True)
            time.sleep(0.5)
        print()  # Newline
        t.join()

    if not INSTALL_SUCCESS:
        print(f"\nInstallation failed: {INSTALL_MESSAGE}")
        sys.exit(1)

    # Final clear and message
    print("\033[H\033[J", end="")  # Clear screen
    print(f"✨ {INSTALL_NAME} SETUP COMPLETE! ✨")
    print("Press F1 to take a screenshot.")


if __name__ == "__main__":
    main()
