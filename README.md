# 📂 terminaltreeview

[![PyPI version](https://img.shields.io/pypi/v/terminaltreeview.svg)](https://pypi.org/project/terminaltreeview/)
[![Python Version](https://img.shields.io/pypi/pyversions/terminaltreeview.svg)](https://pypi.org/project/terminaltreeview/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**terminaltreeview** is a sleek, interactive terminal directory navigator designed specifically for **Windows**. It brings a modern, tree-like navigation experience directly to your command line, allowing you to jump between folders with fluid keyboard shortcuts.

---

## Features

- **Visual Tree View**: Navigate your folders inside a clean, rounded box that fills the terminal window and follows its size. When you leave, your terminal comes back exactly as it was.
- **Magic CD**: Leave the tree and your terminal is already in the folder you picked (PowerShell 7, Windows PowerShell 5.1 and CMD).
- **Type to Search**: Fuzzy, accent-insensitive search (`relatorios` finds `Relatórios`). Search everything on screen, only inside the selected folder, or also inside closed subfolders.
- **Settings Screen**: Press `F2` to choose how the search works, which key does each action, and how the tree looks. Everything is saved to a plain, commented config file.
- **Clean Listing**: Respects Windows hidden/system attributes (`Ctrl + H` shows them) and marks empty or inaccessible folders.
- **Unicode-safe**: Accents in folder names and in what you type just work.
- **Rich Styling**: Colors and icons powered by the `rich` library, with an ASCII mode and a no-color theme.

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
> This command automatically configures every shell it detects — PowerShell 7 (`pwsh`), Windows PowerShell 5.1, and CMD (via a `ttv.bat` shim on your PATH). After running it, simply **restart your terminal** or run `. $PROFILE`.

> [!NOTE]
> Upgrading from 0.3 or older? Run `ttv-setup` again so the PowerShell function reads paths as UTF-8 (folders with any character, not only accents).

**What `ttv-setup` does — nothing hidden:**
- Appends a clearly marked, human-readable block (`# >>> terminaltreeview >>>` … `# <<< terminaltreeview <<<`) containing the plain `ttv` function to your PowerShell profiles. It is static code you can open and read — no `Invoke-Expression`, no downloads, no dynamic execution.
- Creates a small `ttv.bat` shim in Python's Scripts folder for CMD support.
- Running it again is safe: the block is replaced in place, never duplicated. It also migrates profiles configured by older versions.

To completely undo the integration at any time:
```powershell
ttv-setup --uninstall
```

### 3. Start Navigating
Now just type `ttv` from anywhere:
```powershell
ttv              # start in the current folder
ttv D:\projects  # start somewhere else
ttv --help
```

---

## Key Mappings

These are the defaults. Every one of them can be changed in the settings screen (`F2`).

| Key | Action |
| :--- | :--- |
| `↑` / `↓` | Move selection |
| `PgUp` / `PgDn`, `Home` / `End` | Jump through long lists |
| `Enter` / `→` | Expand or collapse folder |
| `←` | Collapse, or jump to the parent folder |
| `Shift + Enter` | **Exit into the selected folder** |
| `Ctrl + Enter` | Exit into the folder of the selected item |
| `Ctrl + O` | Open with the default app (asks first for executables) |
| `Ctrl + N` | Create a new folder in the selected directory |
| `Ctrl + H` / `Alt + H` | Show or hide hidden items |
| `F5` | Refresh |
| `F2` | Settings |
| Type letters | Search |
| `Backspace` | Edit the search |
| `Esc` | Clear the search, or quit |
| `Ctrl + C` | Quit |

---

## Search

Start typing at any time. Matching letters are highlighted, the best match is pre-selected, and `Esc` brings the full tree back with the cursor on the item you were at.

Choose where the search looks in the settings screen:

| Setting | Options |
| :--- | :--- |
| Search in | **Everything on screen** (open folders) or **Selected folder only** |
| Search closed subfolders | Also look inside folders you have not opened, up to a depth you choose |
| Match type | **Fuzzy** (`tst` finds `test_app.py`), **Contains the text**, or **Starts with the text** |

`Enter` on a result opens it in the tree; `Shift + Enter` goes straight into it.

---

## Settings

Press `F2` inside `ttv`:

- `↑` / `↓` to move, `←` / `→` to change a value
- On a key: `Enter` sets a new key, `+` adds an extra one, `Del` removes them
- `R` restores the default of the selected line; `Esc` goes back

Changes are applied and saved immediately to `%APPDATA%\terminaltreeview\config.toml` (use the `TTV_CONFIG` environment variable or `--config` to pick another file). The file is commented and can also be edited by hand:

```toml
[search]
scope = "folder"      # "screen" or "folder"
recursive = true
max_depth = 4

[files]
show_hidden = false
dirs_only = false

[layout]
icons = "emoji"       # "emoji", "ascii" or "none"
help_bar = "compact"  # "full", "compact" or "hidden"
theme = "default"     # "default", "vivid", "classic" or "mono"
language = "auto"     # "auto", "pt" or "en"

[keys]
go_inside = ["shift+enter", "tab"]
open = ["ctrl+o", "f3"]
```

Letters and digits alone are reserved for typing the search, and `Ctrl + C` always quits. Invalid values fall back to the default and `ttv` tells you which line was ignored.

> [!TIP]
> Working over SSH? `Shift + Enter` may arrive as a plain `Enter` there. Add another key to `go_inside`, like `"tab"`.

---

## Requirements

- **OS**: Windows 10 or later (uses the Win32 console API for drawing and key handling).
- **Python**: 3.10 or higher.
- **Window**: at least 50×14 characters. `ttv` shows a notice when the window is smaller.

---

## 🤝 Contributing

Contributions are welcome! Feel free to open issues or submit pull requests to make `terminaltreeview` even better.

Run the tests with:
```powershell
pip install -e . pytest
python -m pytest
```

**Made with ❤️ by FlipNeves**
