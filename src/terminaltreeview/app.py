import os
import sys
import ctypes
import ctypes.wintypes
import msvcrt
from rich.console import Console
from rich.text import Text

# Windows constant for enabling ANSI/VT escape sequence processing (colors)
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
_kernel32 = ctypes.windll.kernel32
try:
    _user32 = ctypes.windll.user32
except AttributeError:
    _user32 = None  # Fallback for non-Windows (though this app is Windows-focused)

VK_SHIFT = 0x10


class _COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.wintypes.SHORT), ("Y", ctypes.wintypes.SHORT)]


class _CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", _COORD),
        ("dwCursorPosition", _COORD),
        ("wAttributes", ctypes.wintypes.WORD),
        ("srWindow", ctypes.wintypes.SMALL_RECT),
        ("dwMaximumWindowSize", _COORD),
    ]


def _enable_vt_processing(file_obj):
    """Enable ANSI escape code processing on a specific file handle (for colors)."""
    try:
        handle = msvcrt.get_osfhandle(file_obj.fileno())
        mode = ctypes.c_ulong()
        _kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        _kernel32.SetConsoleMode(handle, mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass


class TreeNode:
    """Represents a single entry in the flat navigation list."""
    __slots__ = ('path', 'name', 'depth', 'is_dir', 'is_expanded')

    def __init__(self, path: str, name: str, depth: int, is_dir: bool, is_expanded: bool = False):
        self.path = path
        self.name = name
        self.depth = depth
        self.is_dir = is_dir
        self.is_expanded = is_expanded


class DirectoryNavigator:
    def __init__(self, root_dir=None):
        self.initial_root = os.path.abspath(root_dir or os.getcwd())
        self.root_dir = self.initial_root

        # Open CONOUT$ — always points to the active console buffer,
        # regardless of stdout/stderr pipe redirections.
        self._con_stream = open('CONOUT$', 'w', encoding='utf-8')
        _enable_vt_processing(self._con_stream)

        # Get the raw Win32 handle for direct console API calls (cursor control)
        self._con_handle = msvcrt.get_osfhandle(self._con_stream.fileno())

        self.console = Console(
            file=self._con_stream,
            force_terminal=True,
            color_system="truecolor",
        )

        self.selected_index = 0
        self.expanded_dirs: set[str] = set()
        self.flat_list: list[TreeNode] = []
        self._rebuild_flat_list()
        self._render_start_y = None   # Y position where last render started
        self._render_line_count = 0   # Number of terminal lines in last render

    def _list_dir_contents(self, dir_path: str) -> list[tuple[str, bool]]:
        """List contents of a directory, returning (name, is_dir) sorted: dirs first, then files."""
        try:
            entries = os.listdir(dir_path)
        except PermissionError:
            return []

        dirs = []
        files = []
        for name in entries:
            if name.startswith('.'):
                continue
            full = os.path.join(dir_path, name)
            if os.path.isdir(full):
                dirs.append((name, True))
            else:
                files.append((name, False))

        dirs.sort(key=lambda x: x[0].lower())
        files.sort(key=lambda x: x[0].lower())
        return dirs + files

    def _rebuild_flat_list(self):
        """Build the flat navigation list by walking expanded directories."""
        self.flat_list = []
        self._walk_dir(self.root_dir, depth=0)
        if self.selected_index >= len(self.flat_list):
            self.selected_index = max(0, len(self.flat_list) - 1)

    def _walk_dir(self, dir_path: str, depth: int):
        """Recursively walk the directory, adding expanded children."""
        contents = self._list_dir_contents(dir_path)
        for name, is_dir in contents:
            full_path = os.path.join(dir_path, name)
            expanded = full_path in self.expanded_dirs
            node = TreeNode(
                path=full_path,
                name=name,
                depth=depth,
                is_dir=is_dir,
                is_expanded=expanded,
            )
            self.flat_list.append(node)
            if is_dir and expanded:
                self._walk_dir(full_path, depth + 1)

    def render(self, viewport=None) -> Text:
        """Render the tree as a Rich Text object.
        
        Args:
            viewport: Optional tuple (view_start, view_end) to limit which
                      items from flat_list are rendered. If None, renders all.
        """
        output = Text()

        # Dynamic breadcrumb: shows full path to the selected item
        if self.flat_list and 0 <= self.selected_index < len(self.flat_list):
            selected_path = self.flat_list[self.selected_index].path
        else:
            selected_path = self.root_dir
        output.append(f"  {selected_path}", style="dim")
        output.append("\n")

        # Root header
        root_name = os.path.basename(self.root_dir) or self.root_dir
        output.append("  ", style="")
        output.append(f"▼ ", style="bold white")
        output.append(f"📂 {root_name}", style="bold blue")
        output.append("\n")

        # Determine the slice of flat_list to render
        if viewport is not None:
            view_start, view_end = viewport
        else:
            view_start, view_end = 0, len(self.flat_list)

        # Scroll-up indicator
        if view_start > 0:
            output.append(f"    ↑ {view_start} more...\n", style="dim italic")

        # Tree entries (only items within the viewport)
        for i in range(view_start, view_end):
            node = self.flat_list[i]
            is_selected = (i == self.selected_index)
            indent = "    " + "    " * node.depth

            if is_selected:
                marker = "› "
                base_style = "bold cyan"
            else:
                marker = "  "
                base_style = "white"

            output.append(indent, style="")

            if node.is_dir:
                arrow = "▼ " if node.is_expanded else "▶ "
                output.append(arrow, style=base_style)
                icon = "📂 " if node.is_expanded else "📁 "
                output.append(icon, style="")
                output.append(node.name, style=base_style)
            else:
                output.append("  ", style="")  # space where arrow would be
                output.append("M⁺ ", style="green" if not is_selected else "bold cyan")
                output.append(node.name, style=base_style)

            output.append("\n")

        # Scroll-down indicator
        remaining = len(self.flat_list) - view_end
        if remaining > 0:
            output.append(f"    ↓ {remaining} more...\n", style="dim italic")

        # Help bar with keyboard shortcuts
        output.append("\n")
        output.append("  ↑↓", style="bold white")
        output.append(" Navigate  ", style="dim")
        output.append("Enter/→", style="bold white")
        output.append(" Expand  ", style="dim")
        output.append("Ctrl+Enter", style="bold white")
        output.append(" Go Parent  ", style="dim")
        output.append("Shift+Enter", style="bold white")
        output.append(" Go Inside  ", style="dim")
        output.append("← ", style="bold white")
        output.append("Back  ", style="dim")
        output.append("Q", style="bold white")
        output.append(" Quit", style="dim")
        output.append("\n")

        return output

    def _get_cursor_y(self) -> int:
        """Read cursor Y position from the Win32 Console API."""
        csbi = _CONSOLE_SCREEN_BUFFER_INFO()
        _kernel32.GetConsoleScreenBufferInfo(self._con_handle, ctypes.byref(csbi))
        return csbi.dwCursorPosition.Y

    def _get_buffer_info(self) -> _CONSOLE_SCREEN_BUFFER_INFO:
        """Read full console screen buffer info."""
        csbi = _CONSOLE_SCREEN_BUFFER_INFO()
        _kernel32.GetConsoleScreenBufferInfo(self._con_handle, ctypes.byref(csbi))
        return csbi

    def _get_visible_height(self) -> int:
        """Read the visible window height from the console buffer."""
        csbi = self._get_buffer_info()
        return csbi.srWindow.Bottom - csbi.srWindow.Top + 1

    def _compute_viewport(self, visible_height: int) -> tuple[int, int] | None:
        """Compute the (start, end) slice of flat_list to display.
        
        Returns None if all items fit within the visible height.
        
        Layout budget:
          - 2 lines: breadcrumb + root header
          - 1 line: scroll-up indicator (if needed)
          - 1 line: scroll-down indicator (if needed)
          - 1 line: safety margin (cursor line)
        """
        total = len(self.flat_list)
        # Reserve lines for: breadcrumb (1) + root header (1) + help bar (2) + safety margin (1)
        header_lines = 5
        max_items = visible_height - header_lines

        if max_items <= 0:
            max_items = 1  # Always show at least 1 item

        if total <= max_items:
            return None  # Everything fits, no viewport needed

        # Account for scroll indicator lines (they take space from items)
        # We'll always have at least a down-indicator when viewport is active
        # and potentially an up-indicator too
        sel = self.selected_index

        # Calculate window centered on selected_index
        half = max_items // 2
        start = sel - half
        end = start + max_items

        # Clamp to bounds
        if start < 0:
            start = 0
            end = max_items
        if end > total:
            end = total
            start = max(0, end - max_items)

        # Shrink window to account for indicator lines
        if start > 0:
            # Up indicator takes 1 line, so show 1 fewer item
            end = min(total, start + max_items - 1)
        if end < total:
            # Down indicator takes 1 line, so show 1 fewer item
            if start > 0:
                end = min(total, start + max_items - 2)
            else:
                end = min(total, start + max_items - 1)

        # Re-clamp after adjustments to ensure selected_index is visible
        if sel >= end:
            end = sel + 1
            start = max(0, end - max_items + (2 if end < total else 0) + (1 if start > 0 else 0))
        if sel < start:
            start = sel
            end = min(total, start + max_items - (1 if start > 0 else 0) - (1 if start + max_items < total else 0))

        return (start, end)

    def clear_previous_render(self):
        """Clear previously rendered content using Win32 Console API.
        
        Uses _render_start_y and _render_line_count which were calculated
        AFTER the last print (scroll-proof).
        """
        if self._render_start_y is None:
            return
        self._con_stream.flush()
        csbi = self._get_buffer_info()
        buf_width = csbi.dwSize.X
        origin = _COORD(0, self._render_start_y)
        count = buf_width * (self._render_line_count + 1)
        written = ctypes.c_ulong()
        _kernel32.FillConsoleOutputCharacterW(
            self._con_handle, ord(' '), count, origin, ctypes.byref(written))
        _kernel32.FillConsoleOutputAttribute(
            self._con_handle, csbi.wAttributes, count, origin, ctypes.byref(written))
        _kernel32.SetConsoleCursorPosition(self._con_handle, origin)

    def _print_and_track(self, rendered: Text):
        """Print rendered content and record its position (scroll-proof).
        
        After Rich prints, we read the cursor Y and subtract the line count
        to find where the content actually starts. This works correctly
        even if the console scrolled during printing.
        """
        # Count lines via Rich capture (accounts for line wrapping)
        with self.console.capture() as capture:
            self.console.print(rendered, end="")
        raw_output = capture.get()
        line_count = raw_output.count('\n')

        # Actually write to the console
        self._con_stream.write(raw_output)
        self._con_stream.flush()

        # Read post-print cursor Y
        post_y = self._get_cursor_y()

        # start_y = post_y - line_count is ALWAYS correct:
        # - No scroll:  post_y = pre_y + lines → start_y = pre_y ✓
        # - Scroll by S: post_y = pre_y + lines - S, pre_y shifted to pre_y - S
        #                → start_y = pre_y - S ✓
        self._render_start_y = max(0, post_y - line_count)
        self._render_line_count = line_count

    def get_key(self):
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            scan = msvcrt.getch()
            return {b'H': 'up', b'P': 'down', b'M': 'right', b'K': 'left'}.get(scan)
        if ch == b'\r':
            if _user32 and (_user32.GetKeyState(VK_SHIFT) & 0x8000):
                return 'shift_enter'
            return 'enter'
        if ch == b'\x0a': return 'ctrl_enter'
        if ch == b'\x03': return 'ctrl_c'
        if ch == b'q': return 'quit'
        return None

    def _toggle_expand(self, node: TreeNode):
        """Expand or collapse a directory node."""
        if node.is_expanded:
            # Collapse: remove from expanded set (and any children)
            self._collapse_recursive(node.path)
        else:
            self.expanded_dirs.add(node.path)
        self._rebuild_flat_list()

    def _collapse_recursive(self, dir_path: str):
        """Remove a directory and all its sub-expansions from expanded_dirs."""
        self.expanded_dirs.discard(dir_path)
        to_remove = [p for p in self.expanded_dirs if p.startswith(dir_path + os.sep)]
        for p in to_remove:
            self.expanded_dirs.discard(p)

    def _navigate_up(self):
        """Go up one level — if already at or above initial_root, reset the root."""
        parent = os.path.dirname(self.root_dir)
        if parent == self.root_dir:
            return  # Already at filesystem root
        self.root_dir = parent
        # If we went above the initial root, update it and reset expansions
        if not self.root_dir.startswith(self.initial_root):
            self.initial_root = self.root_dir
        self.expanded_dirs.clear()
        self._rebuild_flat_list()
        self.selected_index = 0

    def run(self):
        while True:
            self.clear_previous_render()

            viewport = self._compute_viewport(self._get_visible_height())
            rendered = self.render(viewport)
            self._print_and_track(rendered)

            key = self.get_key()

            if key == 'up':
                if len(self.flat_list) > 0:
                    self.selected_index = (self.selected_index - 1) % len(self.flat_list)
            elif key == 'down':
                if len(self.flat_list) > 0:
                    self.selected_index = (self.selected_index + 1) % len(self.flat_list)
            elif key in ('enter', 'right'):
                if len(self.flat_list) > 0:
                    node = self.flat_list[self.selected_index]
                    if node.is_dir:
                        self._toggle_expand(node)
            elif key == 'left':
                if len(self.flat_list) > 0:
                    node = self.flat_list[self.selected_index]
                    if node.is_dir and node.is_expanded:
                        # Collapse the currently selected expanded directory
                        self._toggle_expand(node)
                    elif node.depth > 0:
                        # Jump to parent directory in the tree
                        target_depth = node.depth - 1
                        for i in range(self.selected_index - 1, -1, -1):
                            if self.flat_list[i].depth == target_depth:
                                self.selected_index = i
                                break
                    else:
                        # Go up to parent directory of the tree root
                        self._navigate_up()
                else:
                    self._navigate_up()
            elif key == 'ctrl_enter':
                self.clear_previous_render()
                if len(self.flat_list) > 0:
                    node = self.flat_list[self.selected_index]
                    return os.path.dirname(node.path)
                return self.root_dir
            elif key == 'shift_enter':
                self.clear_previous_render()
                if len(self.flat_list) > 0:
                    node = self.flat_list[self.selected_index]
                    if node.is_dir:
                        return node.path
                    else:
                        return os.path.dirname(node.path)
                return self.root_dir
            elif key in ('quit', 'ctrl_c'):
                self.clear_previous_render()
                return None


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        shell = sys.argv[2] if len(sys.argv) > 2 else "powershell"
        if shell == "powershell":
            # Output a single-line function to avoid IEX line-by-line parsing issues
            # We use quotes and -Path for robustness with space-containing paths
            print(
                "function ttv { "
                "$target = ttv-tool @args; "
                "if ($target -and (Test-Path -Path $target)) { Set-Location -Path \"$target\" } "
                "}"
            )
        elif shell == "cmd":
            print("To use ttv in CMD, create a ttv.bat file in your PATH with:\n"
                  "@echo off\n"
                  "for /f \"tokens=*\" %%i in ('ttv-tool %*') do cd /d \"%%i\"")
        return

    nav = DirectoryNavigator()
    result = nav.run()
    if result:
        sys.stdout.write(result + '\n')
        sys.stdout.flush()


if __name__ == "__main__":
    main()
