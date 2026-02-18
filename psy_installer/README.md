# Psychedelic Installer Template

This folder contains a ready-to-use template for creating your own "Hypno-Installer" for any project.

## How to use

1.  **Copy the files:**
    Copy `installer_template.py` and `pyproject.toml` to your project's root directory.

2.  **Customize the script:**
    Open `installer_template.py` and edit the following:
    
    *   **Change the Name:**
        ```python
        INSTALL_NAME = "YOUR PROJECT NAME"
        ```
    
    *   **Add your installation logic:**
        Find the `run_installation()` function and add your commands.
        ```python
        def run_installation():
            global INSTALL_SUCCESS, INSTALL_MESSAGE
            try:
                # Update status message
                INSTALL_MESSAGE = "Installing dependencies..."
                
                # Run your commands (example)
                subprocess.run(["npm", "install"], check=True)
                
                # Update status again
                INSTALL_MESSAGE = "Building project..."
                time.sleep(2) 
                
                INSTALL_SUCCESS = True
            except Exception as e:
                # ... handle errors
        ```

3.  **Run it with `uv`:**
    
    ```bash
    # Install dependencies and run
    uv run installer_template.py
    ```

    *Alternatively, you can install `asciimatics` manually:*
    ```bash
    pip install asciimatics
    python3 installer_template.py
    ```

## Customization Tips

*   **Colors:** The `Plasma` effect automatically adapts to your terminal's color depth.
*   **Fonts:** Change `font='big'` in `FigletText` to other standard figlet fonts like `'slant'`, `'banner'`, or `'standard'`.
*   **Effects:** You can add more effects like `Stars` or `Cycle` to the `effects` list in the `demo()` function.
