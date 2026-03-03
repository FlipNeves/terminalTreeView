# Tech Stack

## Core Language
- **Python:** Selected for its rich ecosystem of terminal libraries and ease of development. Python's versatility across Windows and Unix-like systems makes it an ideal choice for a cross-platform TUI tool.

## Terminal UI (TUI) Framework
- **Textual / Rich:** 
    - **Textual:** A modern TUI framework built on top of the 'Rich' library, enabling the creation of highly interactive and visually appealing terminal applications with a reactive architecture.
    - **Rich:** Used for sophisticated text formatting, styling, and basic TUI components, ensuring a 'Rich TUI' experience.

## Shell Integration & 'CD' Mechanism
- **Native Shell Wrappers:** Since a standard process cannot change its parent's current working directory, the tool will provide native shell wrappers (e.g., '.ps1' for PowerShell, '.bat' for CMD, and shell functions for Bash/Zsh). These wrappers will execute the Python tool and then perform the 'cd' command based on the tool's output.

## Distribution & Management
- **Pip (Python Package Index):** The tool will be packaged and distributed via Pip, allowing users to install it easily with 'pip install terminaltreeview'.
- **Python Version:** Targeted at Python 3.9+ to leverage modern language features and TUI library support.

## Dependencies
- **textual:** For the core interactive TUI and tree visualization.
- **rich:** For enhanced text rendering and styling within the TUI.
- **click / argparse:** For handling command-line arguments and configuration.
