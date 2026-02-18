#!/usr/bin/env python3
import os
import subprocess
import sys


def run_command(command, error_message="Command failed"):
    """Run a shell command and handle potential errors."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print(f"Successfully executed: {command}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"{error_message}: {e}")
        print(f"Error output: {e.stderr}")
        # Continue execution despite errors in some cases, but for setup, maybe strict is better.
        pass


def check_and_install(package, command_name=None):
    """Check if a package is installed, and install it if not."""
    cmd_to_check = command_name if command_name else package
    check_cmd = f"which {cmd_to_check}"

    # Only run update if we actually need to install
    install_cmd = f"sudo apt install -y {package}"

    if (
        subprocess.run(
            check_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ).returncode
        != 0
    ):
        print(f"{package} (command: {cmd_to_check}) not found, installing...")
        # Update once if we can, but simplicity implies just install
        run_command(f"sudo apt update && {install_cmd}", f"Failed to install {package}")
    else:
        print(f"{package} is already installed.")


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
    print(f"Created wrapper script at {script_path}")


def setup_gnome_keybinding(command, binding, name="Snipaster"):
    """Set up GNOME custom keybinding using gsettings."""
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    key = "custom-keybindings"

    # Get current bindings
    try:
        current = subprocess.check_output(
            ["gsettings", "get", schema, key], text=True
        ).strip()
    except subprocess.CalledProcessError:
        print("Failed to get gsettings. Skipping GNOME keybinding.")
        return

    # Parse list (handling @as [] empty case)
    if current == "@as []" or current == "[]":
        bindings = []
    else:
        # Simple parsing stripping brackets and quotes
        current = current.strip("[]")
        if not current:
            bindings = []
        else:
            bindings = [b.strip().strip("'") for b in current.split(",")]

    # Check for existing binding with same command to avoid duplicates?
    # For now, just find a free slot.
    path_base = (
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom"
    )

    # Find free slot
    idx = 0
    new_path = ""
    while True:
        path = f"{path_base}{idx}/"
        if path not in bindings:
            new_path = path
            break
        idx += 1

    bindings.append(new_path)

    # Set list
    # formatting list string for gsettings: "['path1', 'path2']"
    bindings_str = "[" + ", ".join([f"'{b}'" for b in bindings]) + "]"
    run_command(f'gsettings set {schema} {key} "{bindings_str}"')

    # Set binding details
    rel_schema = f"{schema}.custom-keybinding:{new_path}"
    run_command(f"gsettings set {rel_schema} name '{name}'")
    run_command(f"gsettings set {rel_schema} command '{command}'")
    run_command(f"gsettings set {rel_schema} binding '{binding}'")
    print(f"Configured GNOME keybinding '{binding}' for {name}")


def setup_screenshot_tool():
    """Set up screenshot tool with F1 binding and clipboard support."""
    # Install required packages
    # Check dependencies: scrot (X11), xbindkeys (X11), xclip (X11/Fallback), gnome-screenshot (Wayland), wl-clipboard (Wayland)
    packages_map = {
        "scrot": "scrot",
        "xbindkeys": "xbindkeys",
        "xclip": "xclip",
        "gnome-screenshot": "gnome-screenshot",
        "wl-clipboard": "wl-copy",
    }

    for pkg, cmd in packages_map.items():
        check_and_install(pkg, cmd)

    # Create directories if they don't exist
    screenshot_dir = os.path.expanduser("~/Pictures/Screenshots")
    autostart_dir = os.path.expanduser("~/.config/autostart")
    os.makedirs(screenshot_dir, exist_ok=True)
    os.makedirs(autostart_dir, exist_ok=True)

    # Create wrapper script
    script_path = os.path.expanduser("~/.local/bin/snipaster_shot")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    create_wrapper_script(script_path)

    # Detect session
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")

    print(f"Detected session: {session_type}, Desktop: {desktop}")

    if "wayland" in session_type.lower() and "gnome" in desktop.lower():
        print("Configuring for GNOME Wayland...")
        setup_gnome_keybinding(script_path, "F1")

        # Disable xbindkeys if running
        run_command("killall xbindkeys 2>/dev/null || true", "Stopping xbindkeys")

        # Remove xbindkeys autostart if exists
        autostart_file = os.path.join(autostart_dir, "xbindkeys.desktop")
        if os.path.exists(autostart_file):
            os.remove(autostart_file)
            print("Removed xbindkeys autostart (not needed for Wayland)")

    else:
        # X11 or other Setup
        print("Configuring for X11/Other using xbindkeys...")

        # Write xbindkeys configuration
        xbindkeys_config = os.path.expanduser("~/.xbindkeysrc")
        config_content = f"""
# Snipaster keybinding
"{script_path}"
  F1
"""
        with open(xbindkeys_config, "w") as f:
            f.write(config_content)
        print(f"Configured xbindkeys at {xbindkeys_config}")

        # Write autostart configuration
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
        print(f"Added xbindkeys to autostart at {autostart_file}")

        # Restart xbindkeys to apply changes
        run_command(
            "killall xbindkeys 2>/dev/null || true && xbindkeys &",
            "Failed to restart xbindkeys",
        )
        print("xbindkeys restarted with new configuration.")


if __name__ == "__main__":
    print("Setting up Snipaster screenshot tool...")
    setup_screenshot_tool()
    print("Setup complete. Press F1 to take a screenshot.")
