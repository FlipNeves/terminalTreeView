import os
import sys
import ctypes
import msvcrt
from rich.console import Console
from rich.text import Text

# Windows constants for enabling ANSI/VT processing on the console
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
_STD_OUTPUT_HANDLE = -11


def _enable_vt_processing():
    """Enable ANSI escape code processing on the Windows console."""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(_STD_OUTPUT_HANDLE)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass  # Non-Windows or restricted environment — colors will degrade gracefully


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

        # Open CONOUT$ — the Windows console device that ALWAYS points to the
        # active console buffer, regardless of stdout/stderr pipe redirections.
        # This guarantees colors work even when called from a shell wrapper.
        _enable_vt_processing()
        self._con_stream = open('CONOUT$', 'w', encoding='utf-8')
        self.console = Console(
            file=self._con_stream,
            force_terminal=True,
            color_system="truecolor",
        )

        self.selected_index = 0
        self.expanded_dirs: set[str] = set()
        self.flat_list: list[TreeNode] = []
        self._rebuild_flat_list()
        self.last_line_count = 0

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

    def render(self) -> Text:
        """Render the tree as a Rich Text object."""
        output = Text()

        # Breadcrumb: full path so the user always knows where they are
        output.append(f"  {self.root_dir}", style="dim")
        output.append("\n")

        # Root header
        root_name = os.path.basename(self.root_dir) or self.root_dir
        output.append("  ", style="")
        output.append(f"▼ ", style="bold white")
        output.append(f"📂 {root_name}", style="bold blue")
        output.append("\n")

        # Tree entries
        for i, node in enumerate(self.flat_list):
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

        return output

    def clear_previous_render(self):
        """Move cursor up and clear lines from the previous render."""
        if self.last_line_count > 0:
            for _ in range(self.last_line_count):
                self._con_stream.write("\033[F\033[K")
            self._con_stream.flush()

    def get_key(self):
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            ch = msvcrt.getch()
            return {b'H': 'up', b'P': 'down', b'M': 'right', b'K': 'left'}.get(ch)
        if ch == b'\r': return 'enter'
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

            rendered = self.render()
            self.console.print(rendered, end="")
            self.last_line_count = str(rendered).count('\n')

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
                    else:
                        # Go up to parent directory of the tree root
                        self._navigate_up()
                else:
                    self._navigate_up()
            elif key == 'ctrl_enter':
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


if __name__ == "__main__":
    nav = DirectoryNavigator()
    result = nav.run()
    if result:
        sys.stdout.write(result + '\n')
        sys.stdout.flush()
