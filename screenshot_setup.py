#!/usr/bin/env python3
import os
import subprocess
import sys

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

def check_and_install(package):
    """Check if a package is installed, and install it if not."""
    check_cmd = f"which {package}"
    install_cmd = f"sudo apt update && sudo apt install -y {package}"
    if subprocess.run(check_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0:
        print(f"{package} not found, installing...")
        run_command(install_cmd, f"Failed to install {package}")
    else:
        print(f"{package} is already installed.")

def setup_screenshot_tool():
    """Set up screenshot tool with F1 binding and clipboard support."""
    # Install required packages
    for pkg in ["scrot", "xbindkeys", "xclip"]:
        check_and_install(pkg)

    # Create directories if they don't exist
    screenshot_dir = os.path.expanduser("~/Pictures/Screenshots")
    autostart_dir = os.path.expanduser("~/.config/autostart")
    os.makedirs(screenshot_dir, exist_ok=True)
    os.makedirs(autostart_dir, exist_ok=True)

    # Write xbindkeys configuration
    xbindkeys_config = os.path.expanduser("~/.xbindkeysrc")
    config_content = """
# Bind F1 to take a screenshot with scrot and copy to clipboard with xclip
"scrot -s ~/Pictures/Screenshots/screenshot-%Y-%m-%d-%H-%M-%S.png -e 'xclip -selection clipboard -t image/png -i $f'"
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
    run_command("killall xbindkeys 2>/dev/null || true && xbindkeys &", "Failed to restart xbindkeys")
    print("xbindkeys restarted with new configuration.")

if __name__ == "__main__":
    print("Setting up screenshot tool with F1 binding on Ubuntu...")
    setup_screenshot_tool()
    print("Setup complete. Press F1 to take a screenshot, which will be saved to ~/Pictures/Screenshots/ and copied to clipboard.")