# Tech Stack

## Core Language
- **Python:** Selected for its rich ecosystem of terminal libraries and ease of development. Python's versatility across Windows and Unix-like systems makes it an ideal choice for a cross-platform TUI tool.

## Terminal UI (TUI) Framework
- **Rich & Custom Selection Mechanism:** 
    - **Rich:** Used for sophisticated text formatting, styling, and rendering the directory tree visualization directly to stdout.
    - **Custom Selection Loop:** A minimalist keyboard-driven selection loop (e.g., using `readchar` or `pynput`) to handle navigation without clearing the entire console. This ensures a "shy," minimalist, and truly inline experience.

## Shell Integration & 'CD' Mechanism
- **Native Shell Wrappers:** Since a standard process cannot change its parent's current working directory, the tool will provide native shell wrappers (e.g., '.ps1' for PowerShell, '.bat' for CMD, and shell functions for Bash/Zsh). These wrappers will execute the Python tool and then perform the 'cd' command based on the tool's output.

## Distribution & Management
- **Pip (Python Package Index):** The tool will be packaged and distributed via Pip, allowing users to install it easily with 'pip install terminaltreeview'.
- **Python Version:** Targeted at Python 3.9+ to leverage modern language features and TUI library support.

## Dependencies
- **rich:** For enhanced text rendering and styling of the tree.
- **readchar:** For lightweight, cross-platform keyboard input handling.
- **click / argparse:** For handling command-line arguments and configuration.
