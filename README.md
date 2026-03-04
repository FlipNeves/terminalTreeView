# 📂 terminaltreeview

[![PyPI version](https://img.shields.io/pypi/v/terminaltreeview.svg)](https://pypi.org/project/terminaltreeview/)
[![Python Version](https://img.shields.io/pypi/pyversions/terminaltreeview.svg)](https://pypi.org/project/terminaltreeview/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**terminaltreeview** is a sleek, interactive terminal directory navigator designed specifically for **Windows**. It brings a modern, tree-like navigation experience directly to your command line, allowing you to jump between folders with fluid keyboard shortcuts.

---

## Features

- **Visual Tree View**: Navigate your folders with a clean, indented structure.
- **Lightning Fast**: Optimized for speed and low latency.
- **Intuitive Shortcuts**:
  - `↑ / ↓`: Navigate through files and folders.
  - `Enter / →`: Expand/Collapse directories.
  - `←`: Go to the parent directory (smart jumping).
  - `Ctrl + Enter`: Exit and open the terminal in the **parent** directory.
  - `Shift + Enter`: **Go Inside!** Exit and teleport your terminal into the selected directory.
- **Rich Styling**: Beautiful colors and icons powered by the `rich` library.

---

## One-Minute Setup

Getting the full experience ready is extremely simple:

### 1. Install via pip
```powershell
pip install terminaltreeview
```

### 2. Enable Shell Integration (Magic CD)
To allow `terminaltreeview` to change your terminal's directory (the "Teleport" feature), run this setup command **once**:
```powershell
ttv-setup
```
> [!TIP]
> This command automatically configures your PowerShell profile. After running it, simply **restart your terminal** or run `. $PROFILE`.

### 3. Start Navigating
Now just type `ttv` from anywhere:
```powershell
ttv
```

---

## Key Mappings

| Key | Action |
| :--- | :--- |
| `↑` / `↓` | Move selection |
| `Enter` / `→` | Expand folder |
| `←` | Collapse folder or jump to Parent |
| `Ctrl + Enter` | Open shell at current selection level |
| `Shift + Enter` | **Open shell inside selected folder** |
| `Q` / `Ctrl + C` | Quit |

---

## Requirements

- **OS**: Windows (Uses Win32 API for cursor and key handling).
- **Python**: 3.8 or higher.

---

## 🤝 Contributing

Contributions are welcome! Feel free to open issues or submit pull requests to make `terminaltreeview` even better.

**Made with ❤️ by FlipNeves**
