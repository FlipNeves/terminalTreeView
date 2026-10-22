import argparse
import codecs
import contextlib
import ctypes
import ctypes.wintypes
import msvcrt
import os
import sys

from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

from terminaltreeview import config as cfgmod
from terminaltreeview import fs
from terminaltreeview import keys as keymod
from terminaltreeview.i18n import Translator
from terminaltreeview.search import match
from terminaltreeview.settings_screen import SettingsScreen

_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
_kernel32 = ctypes.windll.kernel32

DEEP_SEARCH_LIMIT = 20000

EXECUTABLE_EXTENSIONS = frozenset({
    ".appref-ms", ".bat", ".cmd", ".com", ".cpl", ".exe", ".hta", ".js", ".jse", ".lnk",
    ".msi", ".pif", ".ps1", ".reg", ".scr", ".vbe", ".vbs", ".wsf", ".wsh",
})

STYLES = {
    "default": {
        "path": "dim", "root": "bold blue", "name": "", "selected": "bold cyan",
        "match": "bold underline yellow", "info": "dim italic", "note": "dim",
        "filter": "bold yellow", "key": "bold", "hint": "dim", "error": "bold red",
        "ok": "bold green", "header": "bold", "value": "cyan", "message": "yellow",
    },
    "classic": {
        "path": "dim", "root": "bold blue", "name": "white", "selected": "bold cyan",
        "match": "bold underline yellow", "info": "dim italic", "note": "dim",
        "filter": "bold yellow", "key": "bold white", "hint": "dim", "error": "bold red",
        "ok": "bold green", "header": "bold white", "value": "cyan", "message": "yellow",
    },
    "mono": {
        "path": "dim", "root": "bold", "name": "", "selected": "reverse",
        "match": "underline", "info": "dim italic", "note": "dim",
        "filter": "bold", "key": "bold", "hint": "dim", "error": "bold",
        "ok": "bold", "header": "bold", "value": "", "message": "bold",
    },
}

ICONS = {
    "emoji": {"open": "▼ ", "closed": "▶ ", "dir_open": "📂 ", "dir": "📁 ", "file": "📄 ", "root": "📂 ", "dir_suffix": ""},
    "none": {"open": "▼ ", "closed": "▶ ", "dir_open": "", "dir": "", "file": "", "root": "", "dir_suffix": ""},
    "ascii": {"open": "- ", "closed": "+ ", "dir_open": "", "dir": "", "file": "", "root": "", "dir_suffix": "\\"},
}

HELP_FULL = ("nav", "expand", "go_here", "go_inside", "back", "open", "new_folder", "toggle_hidden", "settings", "cancel")
HELP_COMPACT = ("nav", "expand", "go_inside", "settings", "cancel")

_CONTINUE = object()


def build_styles(theme: str, overrides: dict) -> dict:
    styles = dict(STYLES.get(theme, STYLES["default"]))
    styles.update(overrides)
    return styles


def compute_window(total: int, selected: int, budget: int) -> tuple[int, int] | None:
    budget = max(1, budget)
    if total <= budget:
        return None
    selected = min(max(selected, 0), total - 1)
    items = budget
    for _ in range(4):
        start = min(max(0, selected - items // 2), total - items)
        fits = budget - (1 if start > 0 else 0) - (1 if start + items < total else 0)
        if fits >= items:
            break
        items = max(1, fits)
    start = min(max(0, selected - items // 2), total - items)
    return start, start + items


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


def _listing_note(listing: fs.Listing) -> tuple[str | None, str | None]:
    if listing.status == "denied":
        return "denied", None
    if listing.status == "error":
        return "error", listing.error
    if listing.entries:
        return None, None
    if listing.hidden:
        return "hidden_only", None
    if listing.files:
        return "no_subfolders", None
    return "empty", None


class TreeNode:
    __slots__ = ('path', 'name', 'depth', 'is_dir', 'is_expanded', 'note', 'detail')

    def __init__(self, path: str, name: str, depth: int, is_dir: bool, is_expanded: bool = False):
        self.path = path
        self.name = name
        self.depth = depth
        self.is_dir = is_dir
        self.is_expanded = is_expanded
        self.note: str | None = None
        self.detail: str | None = None


class DirectoryNavigator:
    def __init__(self, root_dir=None, config: cfgmod.Config | None = None, key_source=None):
        self.initial_root = os.path.abspath(root_dir or os.getcwd())
        self.root_dir = self.initial_root
        self.config = config or cfgmod.Config()
        self._read_key = key_source

        self._con_stream = open('CONOUT$', 'w', encoding='utf-8')
        _enable_vt_processing(self._con_stream)
        self._con_handle = msvcrt.get_osfhandle(self._con_stream.fileno())

        self.console = Console(file=self._con_stream, force_terminal=True, color_system="truecolor")
        self.selected_index = 0
        self.expanded_dirs: set[str] = set()
        self.flat_list: list[TreeNode] = []
        self.filtered_list: list[TreeNode] = []
        self.root_note: tuple[str | None, str | None] = (None, None)
        self._reset_search_state()
        self.creating = False
        self.create_parent: str | None = None
        self.new_folder_name = ""
        self.create_error = ""
        self.message: tuple[str, str] | None = None
        self._pending_open: str | None = None
        self.mode = "tree"
        self.settings: SettingsScreen | None = None
        self.show_hidden = self.config.files.show_hidden
        self.apply_config()
        self._announce_config_warnings()
        self._rebuild_flat_list()
        self._render_start_y = None
        self._render_line_count = 0

    def apply_config(self, changed: str | None = None):
        self.t = Translator(self.config.layout.language)
        self.styles = build_styles(self.config.layout.theme, self.config.colors)
        self.icons = ICONS.get(self.config.layout.icons, ICONS["emoji"])
        self.keymap = self.config.keymap()
        if changed in ("files.show_hidden", "reset"):
            self.show_hidden = self.config.files.show_hidden
        if changed in ("files.show_hidden", "files.dirs_only", "reset"):
            self._refresh_tree()

    def _announce_config_warnings(self):
        warnings = self.config.warnings
        if not warnings:
            return
        code, values = warnings[0]
        text = self.t("config_warning", warning=self.t(code, **values))
        if len(warnings) > 1:
            text += self.t("config_more_warnings", n=len(warnings) - 1)
        self.message = (text, "error")

    def _reset_search_state(self):
        self.filter_text = ""
        self.search_base: str | None = None
        self.search_recursive = False
        self.search_truncated = False
        self.pre_search_path: str | None = None
        self._deep_cache: list[TreeNode] | None = None
        self._last_query = ""
        self._last_matches: list[TreeNode] | None = None
        self._candidate_count = 0
        self._match_positions: dict[int, list[int]] = {}

    def _selected_node(self) -> TreeNode | None:
        if self.filtered_list and 0 <= self.selected_index < len(self.filtered_list):
            return self.filtered_list[self.selected_index]
        return None

    def _select_path(self, path: str) -> bool:
        for i, node in enumerate(self.filtered_list):
            if node.path == path:
                self.selected_index = i
                return True
        return False

    def _rebuild_flat_list(self):
        self.flat_list = []
        self.root_note = self._walk_dir(self.root_dir, depth=0)
        self._last_matches = None
        self._apply_filter()

    def _walk_dir(self, dir_path: str, depth: int) -> tuple[str | None, str | None]:
        listing = fs.list_dir(dir_path, self.show_hidden, self.config.files.dirs_only)
        for entry in listing.entries:
            full_path = os.path.join(dir_path, entry.name)
            expanded = entry.is_dir and full_path in self.expanded_dirs
            node = TreeNode(full_path, entry.name, depth, entry.is_dir, expanded)
            self.flat_list.append(node)
            if expanded:
                node.note, node.detail = self._walk_dir(full_path, depth + 1)
        return _listing_note(listing)

    def _refresh_tree(self):
        node = self._selected_node()
        path = node.path if node is not None else None
        self._deep_cache = None
        self._rebuild_flat_list()
        if path is not None:
            self._select_path(path)

    def _start_search(self):
        node = self._selected_node()
        self.pre_search_path = node.path if node is not None else None
        base = self.root_dir
        if self.config.search.scope == "folder" and node is not None:
            base = node.path if node.is_dir else os.path.dirname(node.path)
        self.search_base = base
        self.search_recursive = self.config.search.recursive
        if not self.search_recursive and base != self.root_dir and base not in self.expanded_dirs:
            self.expanded_dirs.add(base)
            self._rebuild_flat_list()

    def _search_candidates(self) -> list[TreeNode]:
        base = self.search_base or self.root_dir
        if self.search_recursive:
            if self._deep_cache is None:
                self._deep_cache, self.search_truncated = self._walk_deep(base)
            return self._deep_cache
        if base == self.root_dir:
            return self.flat_list
        prefix = os.path.join(base, "")
        return [node for node in self.flat_list if node.path.startswith(prefix)]

    def _walk_deep(self, base: str) -> tuple[list[TreeNode], bool]:
        search = self.config.search
        found, truncated = fs.walk(base, search.max_depth, self.show_hidden, self.config.files.dirs_only,
                                   search.skip, DEEP_SEARCH_LIMIT)
        base_depth = 0 if base == self.root_dir else os.path.relpath(base, self.root_dir).count(os.sep) + 1
        nodes = [TreeNode(path, entry.name, base_depth + depth, entry.is_dir, path in self.expanded_dirs)
                 for path, entry, depth in found]
        return nodes, truncated

    def _apply_filter(self):
        self._match_positions = {}
        if not self.filter_text:
            self.filtered_list = self.flat_list[:]
            self._candidate_count = len(self.flat_list)
            if self.selected_index >= len(self.filtered_list):
                self.selected_index = max(0, len(self.filtered_list) - 1)
            return

        query = self.filter_text
        if self._last_matches is not None and self._last_query and query.startswith(self._last_query):
            pool = self._last_matches
        else:
            pool = self._search_candidates()
            self._candidate_count = len(pool)

        mode = self.config.search.match
        scored: list[tuple[int, TreeNode]] = []
        for node in pool:
            result = match(query, node.name, mode)
            if result is not None:
                scored.append((result[0], node))
                self._match_positions[id(node)] = result[1]
        self._last_query = query
        self._last_matches = [node for _, node in scored]

        if self.search_recursive:
            scored.sort(key=lambda item: (-item[0], item[1].depth, item[1].path.lower()))
            self.filtered_list = [node for _, node in scored]
            self.selected_index = 0
        else:
            self.filtered_list = [node for _, node in scored]
            self.selected_index = max(range(len(scored)), key=lambda i: scored[i][0]) if scored else 0

    def _end_search(self):
        node = self._selected_node()
        current = node.path if node is not None else None
        fallback = self.pre_search_path
        self._reset_search_state()
        self._apply_filter()
        if current is not None and self._select_path(current):
            return
        if fallback is not None:
            self._select_path(fallback)

    def _reveal(self, path: str, expand: bool = False):
        self._reset_search_state()
        root = os.path.normcase(self.root_dir)
        folder = os.path.dirname(path)
        while folder and os.path.normcase(folder) != root:
            self.expanded_dirs.add(folder)
            parent = os.path.dirname(folder)
            if parent == folder:
                break
            folder = parent
        if expand:
            self.expanded_dirs.add(path)
        self._rebuild_flat_list()
        self._select_path(path)

    def _append_name(self, output: Text, node: TreeNode, base_style: str):
        positions = self._match_positions.get(id(node))
        if not positions:
            output.append(node.name, style=base_style)
            return
        marked = set(positions)
        highlight = f"{base_style} {self.styles['match']}".strip()
        for i, ch in enumerate(node.name):
            output.append(ch, style=highlight if i in marked else base_style)

    def _note_text(self, note: str, detail: str | None) -> str:
        if note == "error":
            return self.t("note_error", error=detail or "?")
        return self.t(f"note_{note}")

    def _append_tree_row(self, output: Text, node: TreeNode, style: str):
        icons = self.icons
        output.append("    " + "    " * node.depth)
        if node.is_dir:
            output.append(icons["open"] if node.is_expanded else icons["closed"], style=style)
            output.append(icons["dir_open"] if node.is_expanded else icons["dir"])
            self._append_name(output, node, style)
            output.append(icons["dir_suffix"], style=style)
            if node.is_expanded and node.note:
                output.append("  " + self._note_text(node.note, node.detail), style=self.styles["note"])
        else:
            output.append("  ")
            output.append(icons["file"])
            self._append_name(output, node, style)

    def _append_result_row(self, output: Text, node: TreeNode, style: str):
        icons = self.icons
        output.append("    ")
        output.append(icons["dir"] if node.is_dir else icons["file"])
        self._append_name(output, node, style)
        if node.is_dir:
            output.append(icons["dir_suffix"] or ("" if icons["dir"] else os.sep), style=style)
        base = self.search_base or self.root_dir
        parent = os.path.dirname(node.path)
        if parent != base:
            output.append("  " + os.path.relpath(parent, base), style=self.styles["path"])

    def _filter_line(self) -> str:
        t = self.t
        text = t("filter", text=self.filter_text, count=len(self.filtered_list), total=self._candidate_count)
        extras = []
        if self.search_base and self.search_base != self.root_dir:
            extras.append(t("filter_in", folder=os.path.relpath(self.search_base, self.root_dir)))
        if self.search_recursive:
            extras.append(t("filter_deep"))
        if self.search_truncated:
            extras.append(t("filter_truncated", n=DEEP_SEARCH_LIMIT))
        return text + ("  · " + " · ".join(extras) if extras else "")

    def _help_segments(self) -> list[tuple[str, str]]:
        mode = self.config.layout.help_bar
        if mode == "hidden":
            return []
        keys = self.config.keys
        segments = []
        for name in HELP_COMPACT if mode == "compact" else HELP_FULL:
            if name == "nav":
                up, down = keys.get("up", []), keys.get("down", [])
                if up[:1] == ["up"] and down[:1] == ["down"]:
                    label = "↑↓"
                else:
                    label = "/".join(keymod.display(key) for key in up[:1] + down[:1])
                if label:
                    segments.append((label, self.t("help_navigate")))
                continue
            bound = [keymod.display(key) for key in keys.get(name, [])]
            if not bound:
                continue
            label = "/".join(bound[:2])
            if cell_len(label) > 9:
                label = bound[0]
            segments.append((label, self.t(f"short_{name}")))
        return segments

    def _hint_lines(self, segments: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
        width = max(20, self.console.width - 1)
        lines: list[list[tuple[str, str]]] = []
        current: list[tuple[str, str]] = []
        used = 2
        for keys_text, label in segments:
            size = cell_len(keys_text) + cell_len(label) + 3
            if current and used + size > width:
                lines.append(current)
                current, used = [], 2
            current.append((keys_text, label))
            used += size
        if current:
            lines.append(current)
        return lines

    def _append_hints(self, output: Text, segments: list[tuple[str, str]]):
        for line in self._hint_lines(segments):
            output.append("  ")
            for keys_text, label in line:
                output.append(keys_text, style=self.styles["key"])
                output.append(f" {label}  ", style=self.styles["hint"])
            output.append("\n")

    def _append_create_prompt(self, output: Text):
        t, styles = self.t, self.styles
        output.append("  " + t("new_folder_in", parent=self.create_parent) + "\n", style=styles["path"])
        output.append("  " + self.icons["dir"])
        output.append(self.new_folder_name, style=styles["ok"])
        output.append("█\n", style=styles["ok"])
        if self.create_error:
            output.append(f"  {self.create_error}\n", style=styles["error"])
        self._append_hints(output, [("Enter", t("hint_create")), ("Esc", t("hint_cancel"))])

    def render(self, viewport=None) -> Text:
        if self.mode == "settings" and self.settings is not None:
            return self.settings.render(viewport)
        return self._render_tree(viewport)

    def _render_tree(self, viewport=None) -> Text:
        t, styles, icons = self.t, self.styles, self.icons
        output = Text()

        node = self._selected_node()
        if self.config.layout.show_path:
            output.append(f"  {node.path if node is not None else self.root_dir}", style=styles["path"])
            output.append("\n")

        root_name = os.path.basename(self.root_dir) or self.root_dir
        suffix = icons["dir_suffix"] if not root_name.endswith(os.sep) else ""
        output.append("  ")
        output.append(icons["open"], style=styles["root"])
        output.append(f"{icons['root']}{root_name}{suffix}", style=styles["root"])
        if self.root_note[0]:
            output.append("  " + self._note_text(*self.root_note), style=styles["note"])
        output.append("\n")

        if viewport is not None:
            view_start, view_end = viewport
        else:
            view_start, view_end = 0, len(self.filtered_list)

        if view_start > 0:
            output.append("    " + t("more_above", n=view_start) + "\n", style=styles["info"])

        if self.filter_text and not self.filtered_list:
            output.append("    " + t("no_matches") + "\n", style=styles["info"])

        for i in range(view_start, view_end):
            row = self.filtered_list[i]
            style = styles["selected"] if i == self.selected_index else styles["name"]
            if self.filter_text:
                self._append_result_row(output, row, style)
            else:
                self._append_tree_row(output, row, style)
            output.append("\n")

        remaining = len(self.filtered_list) - view_end
        if remaining > 0:
            output.append("    " + t("more_below", n=remaining) + "\n", style=styles["info"])

        output.append("\n")
        if self.creating:
            self._append_create_prompt(output)
            return output

        if self.filter_text:
            output.append(f"  {self._filter_line()}\n\n", style=styles["filter"])
        if self.message:
            text, kind = self.message
            output.append(f"  {text}\n", style=styles.get(kind, styles["message"]))
        self._append_hints(output, self._help_segments())
        return output

    def _chrome_lines(self) -> int:
        lines = 3 + (1 if self.config.layout.show_path else 0)
        if self.creating:
            return lines + 4
        if self.filter_text:
            lines += 2
        if self.message:
            lines += 1
        return lines + len(self._hint_lines(self._help_segments()))

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
        if self.mode == "settings" and self.settings is not None:
            budget = min(visible_height - self.settings.chrome_lines(), max(self.config.layout.max_items, 18))
            return compute_window(len(self.settings.rows), self.settings.index, budget)
        budget = min(visible_height - self._chrome_lines(), self.config.layout.max_items)
        return compute_window(len(self.filtered_list), self.selected_index, budget)

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

    def _redraw(self):
        self.clear_previous_render()
        viewport = self._compute_viewport(self._get_visible_height())
        self._print_and_track(self.render(viewport))

    def run(self):
        reader = None
        if self._read_key is None:
            reader = keymod.ConsoleKeyReader()
            self._read_key = reader
        try:
            while True:
                self._redraw()
                result = self._handle_key(self._read_key())
                if result is not _CONTINUE:
                    self.clear_previous_render()
                    return result
        except KeyboardInterrupt:
            self.clear_previous_render()
            return None
        finally:
            if reader is not None:
                reader.close()
                self._read_key = None

    def _handle_key(self, key):
        if key is None or key == "resize":
            return _CONTINUE
        if self.mode == "settings" and self.settings is not None:
            outcome = self.settings.handle(key)
            if outcome == "quit":
                return None
            if outcome == "close":
                self.mode = "tree"
                self.settings = None
            return _CONTINUE
        if self.creating:
            return self._handle_create_key(key)
        if key == "ctrl+c":
            return None

        self.message = None
        confirmed, self._pending_open = self._pending_open, None
        action = self.keymap.get(key)
        if action is not None:
            return self._do(action, key, confirmed)
        if key in ("backspace", "shift+backspace"):
            self._backspace()
        elif key == "ctrl+backspace":
            if self.filter_text:
                self._end_search()
        elif len(key) == 1 and key.isprintable():
            self._type(key)
        return _CONTINUE

    def _handle_create_key(self, key: str):
        if key == "enter":
            self._confirm_create()
        elif key == "esc":
            self._cancel_create()
        elif key in ("backspace", "shift+backspace"):
            self.new_folder_name = self.new_folder_name[:-1]
            self.create_error = ""
        elif key == "ctrl+c":
            return None
        elif len(key) == 1 and key.isprintable():
            self.new_folder_name += key
            self.create_error = ""
        return _CONTINUE

    def _do(self, action: str, key: str, confirmed: str | None):
        node = self._selected_node()
        if action == "up":
            self._move(-1, wrap=True)
        elif action == "down":
            self._move(1, wrap=True)
        elif action == "page_up":
            self._move(-self._page_size(), wrap=False)
        elif action == "page_down":
            self._move(self._page_size(), wrap=False)
        elif action == "first":
            self.selected_index = 0
        elif action == "last":
            self.selected_index = max(0, len(self.filtered_list) - 1)
        elif action == "expand":
            self._expand(node)
        elif action == "back":
            self._back(node)
        elif action == "go_inside":
            if node is None:
                return self.root_dir
            return node.path if node.is_dir else os.path.dirname(node.path)
        elif action == "go_here":
            return os.path.dirname(node.path) if node is not None else self.root_dir
        elif action == "open":
            self._open(node, key, confirmed)
        elif action == "new_folder":
            self._begin_create()
        elif action == "toggle_hidden":
            self.show_hidden = not self.show_hidden
            self._refresh_tree()
            self.message = (self.t("hidden_shown" if self.show_hidden else "hidden_hidden"), "info")
        elif action == "refresh":
            self._refresh_tree()
            self.message = (self.t("refreshed"), "info")
        elif action == "settings":
            if self.filter_text:
                self._end_search()
            self.settings = SettingsScreen(self)
            self.mode = "settings"
        elif action == "cancel":
            if not self.filter_text:
                return None
            self._end_search()
        elif action == "quit":
            return None
        return _CONTINUE

    def _page_size(self) -> int:
        return max(1, self.config.layout.max_items - 2)

    def _move(self, delta: int, wrap: bool):
        total = len(self.filtered_list)
        if not total:
            return
        if wrap:
            self.selected_index = (self.selected_index + delta) % total
        else:
            self.selected_index = min(total - 1, max(0, self.selected_index + delta))

    def _type(self, char: str):
        if not self.filter_text:
            self._start_search()
            if self.search_recursive:
                self.message = (self.t("searching"), "info")
                self._redraw()
                self.message = None
        self.filter_text += char
        self._apply_filter()

    def _backspace(self):
        if not self.filter_text:
            return
        self.filter_text = self.filter_text[:-1]
        if self.filter_text:
            self._apply_filter()
        else:
            self._end_search()

    def _expand(self, node: TreeNode | None):
        if node is None:
            return
        if self.filter_text:
            self._reveal(node.path, expand=node.is_dir)
        elif node.is_dir:
            self._toggle_expand(node)

    def _back(self, node: TreeNode | None):
        if node is None:
            self._navigate_up()
            return
        if self.filter_text:
            parent = os.path.dirname(node.path)
            if os.path.normcase(parent) == os.path.normcase(self.root_dir):
                self._navigate_up()
            elif not self._select_path(parent):
                self._reveal(parent)
            return
        if node.is_dir and node.is_expanded:
            self._toggle_expand(node)
        elif node.depth > 0:
            for i in range(self.selected_index - 1, -1, -1):
                if self.filtered_list[i].depth == node.depth - 1:
                    self.selected_index = i
                    break
        else:
            self._navigate_up()

    def _open(self, node: TreeNode | None, key: str, confirmed: str | None):
        startfile = getattr(os, "startfile", None)
        if node is None or startfile is None:
            return
        risky = not node.is_dir and os.path.splitext(node.name)[1].lower() in EXECUTABLE_EXTENSIONS
        if risky and confirmed != node.path:
            self._pending_open = node.path
            self.message = (self.t("open_confirm", name=node.name, key=keymod.display(key)), "message")
            return
        try:
            startfile(node.path)
        except OSError as error:
            self.message = (self.t("open_failed", error=error.strerror or str(error)), "error")

    def _toggle_expand(self, node: TreeNode):
        target_path = node.path
        self._reset_search_state()
        if node.is_expanded:
            self._collapse_recursive(node.path)
        else:
            self.expanded_dirs.add(node.path)
        self._rebuild_flat_list()
        self._select_path(target_path)

    def _begin_create(self):
        node = self._selected_node()
        if node is not None:
            parent = node.path if node.is_dir else os.path.dirname(node.path)
        else:
            parent = self.root_dir
        self.creating = True
        self.create_parent = parent
        self.new_folder_name = ""
        self.create_error = ""

    def _cancel_create(self):
        self.creating = False
        self.new_folder_name = ""
        self.create_error = ""

    def _confirm_create(self):
        name = self.new_folder_name.strip()
        if not name:
            self._cancel_create()
            return
        target = os.path.join(self.create_parent, name)
        try:
            os.makedirs(target, exist_ok=False)
        except FileExistsError:
            self.create_error = self.t("create_exists")
            return
        except OSError as e:
            self.create_error = self.t("create_failed", error=e.strerror or e)
            return

        self._reveal(target)
        self._cancel_create()

    def _collapse_recursive(self, dir_path: str):
        self.expanded_dirs.discard(dir_path)
        to_remove = [p for p in self.expanded_dirs if p.startswith(dir_path + os.sep)]
        for p in to_remove:
            self.expanded_dirs.discard(p)

    def _navigate_up(self):
        previous = self.root_dir
        self._reset_search_state()
        parent = os.path.dirname(self.root_dir)
        if parent == self.root_dir:
            self._apply_filter()
            return
        self.root_dir = parent
        if not self.root_dir.startswith(self.initial_root):
            self.initial_root = self.root_dir
        self.expanded_dirs.clear()
        self._rebuild_flat_list()
        self.selected_index = 0
        self._select_path(previous)


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("terminaltreeview")
    except Exception:
        return "dev"


def _console_code_page() -> int:
    return _kernel32.GetConsoleOutputCP()


def _output_encoding(code_page: int) -> str:
    if code_page in (0, 65001):
        return "utf-8"
    try:
        return codecs.lookup(f"cp{code_page}").name
    except LookupError:
        return "utf-8"


def _write_line(stream, text: str, errors: str = "strict") -> bool:
    if stream is None:
        return False
    if stream.isatty():
        stream.write(text + "\n")
        stream.flush()
        return True
    data = (text + "\n").encode(_output_encoding(_console_code_page()), errors)
    stream.flush()
    stream.buffer.write(data)
    stream.buffer.flush()
    return True


def _report(text: str):
    _write_line(sys.stderr, text, errors="replace")


def _emit_path(path: str, t: Translator) -> int:
    try:
        return 0 if _write_line(sys.stdout, path) else 1
    except UnicodeEncodeError:
        _report(t("encoding_hint"))
        return 1


def _build_parser(t: Translator) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ttv", description=t("cli_description"), add_help=False)
    parser.add_argument("path", nargs="?", help=t("cli_path"))
    parser.add_argument("--config", metavar="FILE", help=t("cli_config"))
    parser.add_argument("--version", action="version", version=f"terminaltreeview {_version()}",
                        help=t("cli_version"))
    parser.add_argument("-h", "--help", action="help", help=t("cli_help"))
    return parser


def main(argv=None):
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list[:1] == ["init"]:
        shell = args_list[1] if len(args_list) > 1 else "powershell"
        if shell == "powershell":
            from terminaltreeview.setup import PS_FUNCTION
            print(PS_FUNCTION)
        elif shell == "cmd":
            print("Run 'ttv-setup' to install a ttv.bat shim on your PATH automatically.")
        return 0

    with contextlib.redirect_stdout(sys.stderr):
        args = _build_parser(Translator()).parse_args(args_list)

    config = cfgmod.load(args.config)
    t = Translator(config.layout.language)
    start = os.getcwd()
    if args.path:
        start = os.path.abspath(os.path.expanduser(args.path))
        if os.path.isfile(start):
            start = os.path.dirname(start)
        elif not os.path.isdir(start):
            _report(t("path_missing", path=args.path))
            return 1

    nav = DirectoryNavigator(start, config=config)
    result = nav.run()
    if result:
        return _emit_path(result, t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
