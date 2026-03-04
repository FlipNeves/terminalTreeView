# terminaltreeview

An interactive terminal directory navigator for Windows with smooth navigation and shell integration.

## Features

- 📁 **Interactive Navigation**: Use arrow keys to explore your file system.
- 🚀 **Fast Shortcuts**: 
  - `Enter / Right Arrow`: Expand directory.
  - `Left Arrow`: Collapse or go to parent directory.
  - `Ctrl + Enter`: Open terminal at the parent level of the selection.
  - `Shift + Enter`: Go inside the selected directory (changes your shell location).
- 🛠️ **Shell Integration**: Automatically syncs your terminal's current directory with your navigation.

## Installation

```powershell
pip install terminaltreeview
```

### Full Experience Setup

After installing, run the following command to enable the `cd` behavior in PowerShell:

```powershell
ttv-setup
```

Then, restart your terminal or run `. $PROFILE`. Now you can just type `ttv` to start navigating.

## Requirements

- Windows OS
- Python 3.8+
