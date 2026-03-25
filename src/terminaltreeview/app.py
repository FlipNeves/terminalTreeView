import os
import sys
import ctypes
import ctypes.wintypes
import msvcrt
from rich.console import Console
from rich.text import Text

_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
_kernel32 = ctypes.windll.kernel32
try:
    _user32 = ctypes.windll.user32
except AttributeError:
    _user32 = None

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
    try:
        handle = msvcrt.get_osfhandle(file_obj.fileno())
        mode = ctypes.c_ulong()
        _kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        _kernel32.SetConsoleMode(handle, mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass


class TreeNode:
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

        self._con_stream = open('CONOUT$', 'w', encoding='utf-8')
        _enable_vt_processing(self._con_stream)
        self._con_handle = msvcrt.get_osfhandle(self._con_stream.fileno())

        self.console = Console(file=self._con_stream, force_terminal=True, color_system="truecolor")
        self.selected_index = 0
        self.expanded_dirs: set[str] = set()
        self.flat_list: list[TreeNode] = []
        self.filtered_list: list[TreeNode] = []
        self.filter_text = ""
        self._rebuild_flat_list()
        self._render_start_y = None   
        self._render_line_count = 0

    def _list_dir_contents(self, dir_path: str) -> list[tuple[str, bool]]:
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
        self.flat_list = []
        self._walk_dir(self.root_dir, depth=0)
        self._apply_filter()

    def _apply_filter(self):
        self.filtered_list = self.flat_list[:]
        if not hasattr(self, 'filter_text') or not self.filter_text:
            if self.selected_index >= len(self.filtered_list):
                self.selected_index = max(0, len(self.filtered_list) - 1)
            return

        lower_filter = self.filter_text.lower()
        
        for i, node in enumerate(self.flat_list):
            if node.name.lower().startswith(lower_filter):
                self.selected_index = i
                return
                
        for i, node in enumerate(self.flat_list):
            if lower_filter in node.name.lower():
                self.selected_index = i
                return

    def _walk_dir(self, dir_path: str, depth: int):
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
        output = Text()

        if self.filtered_list and 0 <= self.selected_index < len(self.filtered_list):
            selected_path = self.filtered_list[self.selected_index].path
        else:
            selected_path = self.root_dir
        output.append(f"  {selected_path}", style="dim")
        output.append("\n")

        root_name = os.path.basename(self.root_dir) or self.root_dir
        output.append("  ", style="")
        output.append(f"▼ ", style="bold white")
        output.append(f"📂 {root_name}", style="bold blue")
        output.append("\n")

        if viewport is not None:
            view_start, view_end = viewport
        else:
            view_start, view_end = 0, len(self.filtered_list)

        if view_start > 0:
            output.append(f"    ↑ {view_start} more...\n", style="dim italic")

        for i in range(view_start, view_end):
            node = self.filtered_list[i]
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
                output.append("  ", style="")  
                output.append("M⁺ ", style="green" if not is_selected else "bold cyan")
                output.append(node.name, style=base_style)

            output.append("\n")

        remaining = len(self.filtered_list) - view_end
        if remaining > 0:
            output.append(f"    ↓ {remaining} more...\n", style="dim italic")

        output.append("\n")
        if self.filter_text:
            output.append(f"  Filter: {self.filter_text}\n\n", style="bold yellow")
            
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
        output.append("Ctrl+O ", style="bold white")
        output.append("Open  ", style="dim")
        output.append("Esc", style="bold white")
        output.append(" Quit/Clear", style="dim")
        output.append("\n")

        return output

    def _get_cursor_y(self) -> int:
        csbi = _CONSOLE_SCREEN_BUFFER_INFO()
        _kernel32.GetConsoleScreenBufferInfo(self._con_handle, ctypes.byref(csbi))
        return csbi.dwCursorPosition.Y

    def _get_buffer_info(self) -> _CONSOLE_SCREEN_BUFFER_INFO:
        csbi = _CONSOLE_SCREEN_BUFFER_INFO()
        _kernel32.GetConsoleScreenBufferInfo(self._con_handle, ctypes.byref(csbi))
        return csbi

    def _get_visible_height(self) -> int:
        csbi = self._get_buffer_info()
        return csbi.srWindow.Bottom - csbi.srWindow.Top + 1

    def _compute_viewport(self, visible_height: int) -> tuple[int, int] | None:
        total = len(self.filtered_list)
        header_lines = 5
        # Decrease standard view size to 12 items for a cleaner look
        max_items = min(visible_height - header_lines, 12)

        if max_items <= 0:
            max_items = 1  

        if total <= max_items:
            return None  

        sel = self.selected_index

        half = max_items // 2
        start = sel - half
        end = start + max_items

        if start < 0:
            start = 0
            end = max_items
        if end > total:
            end = total
            start = max(0, end - max_items)

        if start > 0:
            end = min(total, start + max_items - 1)
        if end < total:
            if start > 0:
                end = min(total, start + max_items - 2)
            else:
                end = min(total, start + max_items - 1)

        if sel >= end:
            end = sel + 1
            start = max(0, end - max_items + (2 if end < total else 0) + (1 if start > 0 else 0))
        if sel < start:
            start = sel
            end = min(total, start + max_items - (1 if start > 0 else 0) - (1 if start + max_items < total else 0))

        return (start, end)

    def clear_previous_render(self):
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
        with self.console.capture() as capture:
            self.console.print(rendered, end="")
        raw_output = capture.get()
        line_count = raw_output.count('\n')

        self._con_stream.write(raw_output)
        self._con_stream.flush()

        post_y = self._get_cursor_y()

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
        if ch == b'\x08': return 'backspace'
        if ch == b'\x1b': return 'escape'
        if ch == b'\x03': return 'ctrl_c'
        if ch == b'\x0f': return 'ctrl_o'
        
        try:
            return ch.decode('utf-8')
        except UnicodeDecodeError:
            return None

    def _toggle_expand(self, node: TreeNode):
        self.filter_text = ""
        if node.is_expanded:
            self._collapse_recursive(node.path)
        else:
            self.expanded_dirs.add(node.path)
        self._rebuild_flat_list()

    def _collapse_recursive(self, dir_path: str):
        self.expanded_dirs.discard(dir_path)
        to_remove = [p for p in self.expanded_dirs if p.startswith(dir_path + os.sep)]
        for p in to_remove:
            self.expanded_dirs.discard(p)

    def _navigate_up(self):
        self.filter_text = ""
        parent = os.path.dirname(self.root_dir)
        if parent == self.root_dir:
            return  
        self.root_dir = parent
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
                if len(self.filtered_list) > 0:
                    self.selected_index = (self.selected_index - 1) % len(self.filtered_list)
            elif key == 'down':
                if len(self.filtered_list) > 0:
                    self.selected_index = (self.selected_index + 1) % len(self.filtered_list)
            elif key in ('enter', 'right'):
                if len(self.filtered_list) > 0:
                    node = self.filtered_list[self.selected_index]
                    if node.is_dir:
                        self._toggle_expand(node)
            elif key == 'left':
                if len(self.filtered_list) > 0:
                    node = self.filtered_list[self.selected_index]
                    if node.is_dir and node.is_expanded:
                        self._toggle_expand(node)
                    elif node.depth > 0:
                        target_depth = node.depth - 1
                        for i in range(self.selected_index - 1, -1, -1):
                            if self.filtered_list[i].depth == target_depth:
                                self.selected_index = i
                                break
                    else:
                        self._navigate_up()
                else:
                    self._navigate_up()
            elif key == 'ctrl_enter':
                self.clear_previous_render()
                if len(self.filtered_list) > 0:
                    node = self.filtered_list[self.selected_index]
                    return os.path.dirname(node.path)
                return self.root_dir
            elif key == 'shift_enter':
                self.clear_previous_render()
                if len(self.filtered_list) > 0:
                    node = self.filtered_list[self.selected_index]
                    if node.is_dir:
                        return node.path
                    else:
                        return os.path.dirname(node.path)
                return self.root_dir
            elif key == 'backspace':
                if self.filter_text:
                    self.filter_text = self.filter_text[:-1]
                    self._apply_filter()
            elif key == 'escape':
                if self.filter_text:
                    self.filter_text = ""
                    self._apply_filter()
                else:
                    self.clear_previous_render()
                    return None
            elif key == 'ctrl_c':
                self.clear_previous_render()
                return None
            elif key == 'ctrl_o':
                if len(self.filtered_list) > 0:
                    node = self.filtered_list[self.selected_index]
                    try:
                        if hasattr(os, 'startfile'):
                            os.startfile(node.path)
                    except Exception:
                        pass
            elif isinstance(key, str) and len(key) == 1 and key.isprintable():
                self.filter_text += key
                self._apply_filter()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        shell = sys.argv[2] if len(sys.argv) > 2 else "powershell"
        if shell == "powershell":
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
