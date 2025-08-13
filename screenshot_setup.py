#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

def get_display_server():
    """Detect the display server (x11 or wayland)."""
    return os.environ.get("XDG_SESSION_TYPE", "x11").lower()

def get_package_manager():
    """Detect the package manager."""
    for pm in ["apt", "dnf", "pacman", "zypper"]:
        if shutil.which(pm):
            return pm
    return None

def run_command(command, error_message="Command failed"):
    """Run a shell command and handle potential errors."""
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"Successfully executed: {command}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"{error_message}: {e}")
        print(f"Error output: {e.stderr}")
        sys.exit(1)

def check_and_install(package_manager, packages):
    """Check if packages are installed and install them if not."""
    pm_commands = {
        "apt": "sudo apt update && sudo apt install -y",
        "dnf": "sudo dnf install -y",
        "pacman": "sudo pacman -Syu --noconfirm",
        "zypper": "sudo zypper install -y"
    }

    install_cmd = pm_commands.get(package_manager)
    if not install_cmd:
        print(f"Unsupported package manager: {package_manager}")
        sys.exit(1)

    for package in packages:
        check_cmd = f"which {package}"
        if subprocess.run(check_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0:
            print(f"{package} not found, installing...")
            run_command(f"{install_cmd} {package}", f"Failed to install {package}")
        else:
            print(f"{package} is already installed.")

def setup_x11():
    """Set up screenshot tool for X11."""
    print("Setting up for X11...")
    package_manager = get_package_manager()
    if not package_manager:
        print("Could not detect a supported package manager (apt, dnf, pacman, zypper).")
        sys.exit(1)

    check_and_install(package_manager, ["scrot", "xbindkeys", "xclip"])

    screenshot_dir = os.path.expanduser("~/Pictures/Screenshots")
    autostart_dir = os.path.expanduser("~/.config/autostart")
    os.makedirs(screenshot_dir, exist_ok=True)
    os.makedirs(autostart_dir, exist_ok=True)

    xbindkeys_config = os.path.expanduser("~/.xbindkeysrc")
    config_content = """
# Bind F1 to take a screenshot with scrot and copy to clipboard with xclip
"scrot -s ~/Pictures/Screenshots/screenshot-%Y-%m-%d-%H-%M-%S.png -e 'xclip -selection clipboard -t image/png -i $f'"
  F1
"""
    with open(xbindkeys_config, "w") as f:
        f.write(config_content)
    print(f"Configured xbindkeys at {xbindkeys_config}")

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

    run_command("killall xbindkeys 2>/dev/null || true && xbindkeys &", "Failed to restart xbindkeys")
    print("xbindkeys restarted. Press F1 to take a screenshot.")

def setup_wayland():
    """Set up screenshot tool for Wayland."""
    print("Setting up for Wayland...")
    package_manager = get_package_manager()
    if not package_manager:
        print("Could not detect a supported package manager (apt, dnf, pacman, zypper).")
        sys.exit(1)

    wayland_packages = ["grim", "slurp", "wl-clipboard"]

    check_and_install(package_manager, wayland_packages)

    script_dir = os.path.expanduser("~/.local/bin")
    os.makedirs(script_dir, exist_ok=True)

    screenshot_script_path = os.path.join(script_dir, "wayland-screenshot.sh")
    # Corrected the screenshot script to save the file and then copy it.
    screenshot_script_content = f"""
#!/bin/sh
SCREENSHOT_DIR=$(xdg-user-dir PICTURES)/Screenshots
mkdir -p $SCREENSHOT_DIR
FILE_PATH=$SCREENSHOT_DIR/$(date +'%Y-%m-%d-%H%M%S.png')
grim -g "$(slurp)" "$FILE_PATH"
wl-copy < "$FILE_PATH"
"""
    with open(screenshot_script_path, "w") as f:
        f.write(screenshot_script_content)

    os.chmod(screenshot_script_path, 0o755)
    print(f"Screenshot script created at {screenshot_script_path}")

    print("\\n--- MANUAL ACTION REQUIRED ---")
    print("Wayland requires you to set up custom keyboard shortcuts manually through your desktop environment's settings.")
    print("Please add a custom shortcut with the following command:")
    print(f"Command: {screenshot_script_path}")
    print("Assign this command to your desired key (e.g., F1).")
    print("\\nHere are some hints for popular desktop environments:")
    print(" - GNOME: Settings > Keyboard > Keyboard Shortcuts > Custom Shortcuts")
    print(" - KDE Plasma: System Settings > Shortcuts > Custom Shortcuts")
    print(" - Sway/i3: Add `bindsym F1 exec {screenshot_script_path}` to your config file.")
    print("---------------------------------")


def main():
    """Main function to run the setup."""
    print("Starting screenshot tool setup...")
    display_server = get_display_server()
    print(f"Detected display server: {display_server}")

    if display_server == "wayland":
        setup_wayland()
    else:
        setup_x11()

    print("\\nSetup complete.")

if __name__ == "__main__":
    main()