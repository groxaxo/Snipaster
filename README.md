# Snipaster for Ubuntu

Snipaster is a utility script to automate the setup of a screenshot tool on Ubuntu systems. By pressing F1, you can capture a selected area of the screen, save it to a designated folder, and automatically copy it to the clipboard for easy sharing or editing. This setup has been tested on Ubuntu systems with Wayland support.

## Overview

This project provides a Python script that installs and configures the necessary tools (`scrot`, `xbindkeys`, `xclip`) to enable screenshot functionality with a keyboard shortcut. It also sets up the tool to start automatically on login.

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/[username]/Snipaster.git
   cd Snipaster
   ```
2. Make the script executable:
   ```bash
   chmod +x screenshot_setup.py
   ```
3. Run the script:
   ```bash
   ./screenshot_setup.py
   ```

## Usage

- Press `F1` to activate the screenshot tool.
- Click and drag to select the area of the screen you want to capture.
- The screenshot is saved to `~/Pictures/Screenshots/` with a timestamp in the filename.
- The screenshot is automatically copied to the clipboard, allowing you to paste it directly into applications with `Ctrl+V` or right-click and paste.

## Requirements

- Ubuntu or a Debian-based Linux distribution (tested on Linux 5.15 with Wayland support).
- Python 3 for running the setup script.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
