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
from terminaltreeview.layout import (
    BOXES, MIN_HEIGHT, MIN_WIDTH, boxed, centered, clip_start, compute_window, list_rows,
)
from terminaltreeview.search import match
from terminaltreeview.settings_screen import SettingsScreen

_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
_kernel32 = ctypes.windll.kernel32

_ENTER_SCREEN = "\x1b[?1049h\x1b[?25l\x1b[?7l"
_LEAVE_SCREEN = "\x1b[?7h\x1b[?25h\x1b[?1049l"

DEEP_SEARCH_LIMIT = 20000

EXECUTABLE_EXTENSIONS = frozenset({
    ".appref-ms", ".bat", ".cmd", ".com", ".cpl", ".exe", ".hta", ".js", ".jse", ".lnk",
    ".msi", ".pif", ".ps1", ".reg", ".scr", ".vbe", ".vbs", ".wsf", ".wsh",
})

STYLES = {
    "default": {
        "path": "dim", "root": "bold blue", "folder": "bold bright_white", "name": "", "selected": "bold cyan",
        "match": "bold underline yellow", "info": "dim italic", "note": "dim",
        "filter": "bold yellow", "key": "bold", "hint": "dim", "error": "bold red",
        "ok": "bold green", "header": "bold", "value": "cyan", "message": "yellow",
        "border": "dim",
    },
    "vivid": {
        "path": "#7dcfff", "root": "bold #7dcfff", "folder": "bold #7aa2f7", "name": "#c0caf5",
        "selected": "bold #7dcfff", "match": "bold underline #e0af68",
        "info": "italic #737aa2", "note": "italic #737aa2", "filter": "bold #e0af68",
        "key": "bold #bb9af7", "hint": "#a9b1d6", "error": "bold #f7768e", "ok": "bold #9ece6a",
        "header": "bold #bb9af7", "value": "#9ece6a", "message": "#e0af68", "border": "#7aa2f7",
    },
    "classic": {
        "path": "dim", "root": "bold blue", "folder": "bold bright_white", "name": "white",
        "selected": "bold cyan", "match": "bold underline yellow", "info": "dim italic", "note": "dim",
        "filter": "bold yellow", "key": "bold white", "hint": "dim", "error": "bold red",
        "ok": "bold green", "header": "bold white", "value": "cyan", "message": "yellow",
        "border": "blue",
    },
    "mono": {
        "path": "dim", "root": "bold", "folder": "bold", "name": "", "selected": "reverse",
        "match": "underline", "info": "dim italic", "note": "dim",
        "filter": "bold", "key": "bold", "hint": "dim", "error": "bold",
        "ok": "bold", "header": "bold", "value": "", "message": "bold",
        "border": "",
    },
}

ICONS = {
    "emoji": {"open": "▼ ", "closed": "▶ ", "dir_open": "📂 ", "dir": "📁 ", "file": "📄 ", "root": "📂 ", "dir_suffix": ""},
    "none": {"open": "▼ ", "closed": "▶ ", "dir_open": "", "dir": "", "file": "", "root": "", "dir_suffix": ""},
    "ascii": {"open": "- ", "closed": "+ ", "dir_open": "", "dir": "", "file": "", "root": "", "dir_suffix": "\\"},
}

HELP_GROUPS = (
    ("nav", "expand", "back"),
    ("go_here", "go_inside"),
    ("open", "new_folder"),
    ("toggle_hidden", "settings", "cancel"),
)
HELP_COMPACT = frozenset({"nav", "expand", "go_inside", "settings", "cancel"})

_CONTINUE = object()


def build_styles(theme: str, overrides: dict) -> dict:
    styles = dict(STYLES.get(theme, STYLES["default"]))
    styles.update(overrides)
    return styles


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
        self._page_rows = 10
        self._too_small = False
        self._drawn_size: tuple[int, int] | None = None

    def apply_config(self, changed: str | None = None):
        self.t = Translator(self.config.layout.language)
        self.styles = build_styles(self.config.layout.theme, self.config.colors)
        self.icons = ICONS.get(self.config.layout.icons, ICONS["emoji"])
        self.box = BOXES["ascii" if self.config.layout.icons == "ascii" else "rounded"]
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

    def _tree_row(self, node: TreeNode, style: str) -> Text:
        icons = self.icons
        line = Text("  " + "    " * node.depth)
        if node.is_dir:
            line.append(icons["open"] if node.is_expanded else icons["closed"], style=style)
            line.append(icons["dir_open"] if node.is_expanded else icons["dir"])
            self._append_name(line, node, style)
            line.append(icons["dir_suffix"], style=style)
            if node.is_expanded and node.note:
                line.append("  " + self._note_text(node.note, node.detail), style=self.styles["note"])
        else:
            line.append("  ")
            line.append(icons["file"])
            self._append_name(line, node, style)
        return line

    def _result_row(self, node: TreeNode, style: str) -> Text:
        icons = self.icons
        line = Text("  ")
        line.append(icons["dir"] if node.is_dir else icons["file"])
        self._append_name(line, node, style)
        if node.is_dir:
            line.append(icons["dir_suffix"] or ("" if icons["dir"] else os.sep), style=style)
        base = self.search_base or self.root_dir
        parent = os.path.dirname(node.path)
        if parent != base:
            line.append("  " + os.path.relpath(parent, base), style=self.styles["path"])
        return line

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

    def _help_groups(self) -> list[list[tuple[str, str]]]:
        mode = self.config.layout.help_bar
        if mode == "hidden":
            return []
        keys = self.config.keys
        groups = []
        for names in HELP_GROUPS:
            group = []
            for name in names:
                if mode == "compact" and name not in HELP_COMPACT:
                    continue
                if name == "nav":
                    up, down = keys.get("up", []), keys.get("down", [])
                    if up[:1] == ["up"] and down[:1] == ["down"]:
                        label = "↑↓"
                    else:
                        label = "/".join(keymod.display(key) for key in up[:1] + down[:1])
                    if label:
                        group.append((label, self.t("help_navigate")))
                    continue
                bound = [keymod.display(key) for key in keys.get(name, [])]
                if not bound:
                    continue
                label = "/".join(bound[:2])
                if cell_len(label) > 9:
                    label = bound[0]
                group.append((label, self.t(f"short_{name}")))
            if group:
                groups.append(group)
        return groups

    def _hint_lines(self, groups: list[list[tuple[str, str]]], width: int) -> list[list[list[tuple[str, str]]]]:
        def size(piece):
            return sum(cell_len(keys_text) + 1 + cell_len(label) for keys_text, label in piece) + 2 * (len(piece) - 1)

        pieces = []
        for group in groups:
            piece = []
            for segment in group:
                if piece and size(piece + [segment]) > width:
                    pieces.append(piece)
                    piece = []
                piece.append(segment)
            pieces.append(piece)

        lines: list[list[list[tuple[str, str]]]] = []
        current: list[list[tuple[str, str]]] = []
        used = 0
        for piece in pieces:
            needed = size(piece) + (5 if current else 0)
            if current and used + needed > width:
                lines.append(current)
                current, used, needed = [], 0, size(piece)
            current.append(piece)
            used += needed
        if current:
            lines.append(current)
        return lines

    def _hint_texts(self, groups: list[list[tuple[str, str]]], width: int) -> list[Text]:
        separator = self.box[5]
        texts = []
        for line in self._hint_lines(groups, width):
            text = Text()
            for i, piece in enumerate(line):
                if i:
                    text.append(f"  {separator}  ", style=self.styles["hint"])
                for j, (keys_text, label) in enumerate(piece):
                    if j:
                        text.append("  ")
                    text.append(keys_text, style=self.styles["key"])
                    text.append(f" {label}", style=self.styles["hint"])
            texts.append(text)
        return texts

    def _message_lines(self, message: tuple[str, str], width: int) -> list[Text]:
        text, kind = message
        styled = Text(text, style=self.styles.get(kind, self.styles["message"]))
        return list(styled.wrap(self.console, width))[:2]

    def _create_prompt_lines(self, width: int) -> list[Text]:
        t, styles = self.t, self.styles
        room = width - cell_len(t("new_folder_in", parent=""))
        lines = [Text(t("new_folder_in", parent=clip_start(self.create_parent, room)), style=styles["path"])]
        name = Text(self.icons["dir"])
        name.append(clip_start(self.new_folder_name, width - name.cell_len - 1), style=styles["ok"])
        name.append("█", style=styles["ok"])
        lines.append(name)
        if self.create_error:
            lines.append(Text(self.create_error, style=styles["error"]))
        return lines + self._hint_texts([[("Enter", t("hint_create")), ("Esc", t("hint_cancel"))]], width)

    def _tree_footer(self, width: int) -> list[Text]:
        if self.creating:
            return self._create_prompt_lines(width)
        lines = []
        if self.filter_text:
            lines.append(Text(self._filter_line(), style=self.styles["filter"]))
        if self.message:
            lines += self._message_lines(self.message, width)
        return lines + self._hint_texts(self._help_groups(), width)

    def _root_line(self) -> Text:
        icons, styles = self.icons, self.styles
        root_name = os.path.basename(self.root_dir) or self.root_dir
        suffix = icons["dir_suffix"] if not root_name.endswith(os.sep) else ""
        line = Text(icons["open"], style=styles["root"])
        line.append(f"{icons['root']}{root_name}{suffix}", style=styles["root"])
        if self.root_note[0]:
            line.append("  " + self._note_text(*self.root_note), style=styles["note"])
        return line

    def _tree_screen(self, width: int, height: int) -> tuple[str, list[Text], list[Text]]:
        t, styles = self.t, self.styles
        footer = self._tree_footer(width)
        total = len(self.filtered_list)
        window = compute_window(total, self.selected_index, list_rows(height, 1, footer))
        start, end = window if window is not None else (0, total)
        self._page_rows = end - start

        body = [self._root_line()]
        if start > 0:
            body.append(Text("  " + t("more_above", n=start), style=styles["info"]))
        if self.filter_text and not self.filtered_list:
            body.append(Text("  " + t("no_matches"), style=styles["info"]))
        for i in range(start, end):
            node = self.filtered_list[i]
            style = styles["selected"] if i == self.selected_index else styles["folder" if node.is_dir else "name"]
            body.append(self._result_row(node, style) if self.filter_text else self._tree_row(node, style))
        if end < total:
            body.append(Text("  " + t("more_below", n=total - end), style=styles["info"]))

        title = ""
        if self.config.layout.show_path:
            node = self._selected_node()
            title = node.path if node is not None else self.root_dir
        return title, body, footer

    def _too_small_lines(self, width: int, height: int) -> list[Text]:
        t, styles = self.t, self.styles
        quit_key = (self.config.keys.get("cancel") or ["ctrl+c"])[0]
        return centered([
            Text(t("too_small"), style=styles["error"]),
            Text(t("too_small_size", min=f"{MIN_WIDTH}×{MIN_HEIGHT}", now=f"{width}×{height}"),
                 style=styles["info"]),
            Text(t("too_small_quit", key=keymod.display(quit_key)), style=styles["hint"]),
        ], width, height)

    def _frame_lines(self, width: int, height: int) -> list[Text]:
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            return self._too_small_lines(width, height)
        if self.mode == "settings" and self.settings is not None:
            title, body, footer = self.settings.screen(width - 4, height)
        else:
            title, body, footer = self._tree_screen(width - 4, height)
        return boxed(self.box, self.styles, title, body, footer, width, height)

    def render(self, width: int | None = None, height: int | None = None) -> Text:
        if width is None or height is None:
            width, height = self._get_window_size()
        return Text("\n").join(self._frame_lines(width, height))

    def _get_buffer_info(self) -> _CONSOLE_SCREEN_BUFFER_INFO:
        csbi = _CONSOLE_SCREEN_BUFFER_INFO()
        _kernel32.GetConsoleScreenBufferInfo(self._con_handle, ctypes.byref(csbi))
        return csbi

    def _get_window_size(self) -> tuple[int, int]:
        window = self._get_buffer_info().srWindow
        return window.Right - window.Left + 1, window.Bottom - window.Top + 1

    def _redraw(self):
        width, height = self._get_window_size()
        self._too_small = width < MIN_WIDTH or height < MIN_HEIGHT
        frame = Text("\n").join(self._frame_lines(width, height))
        self.console.width = width
        with self.console.capture() as capture:
            self.console.print(frame, end="", no_wrap=True, overflow="crop")
        output = ["\x1b[2J"] if (width, height) != self._drawn_size else []
        self._drawn_size = (width, height)
        for row, line in enumerate(capture.get().split("\n"), 1):
            output.append(f"\x1b[{row};1H{line}")
        self._con_stream.write("".join(output))
        self._con_stream.flush()

    def run(self):
        reader = None
        if self._read_key is None:
            reader = keymod.ConsoleKeyReader()
            self._read_key = reader
        self._con_stream.write(_ENTER_SCREEN)
        self._drawn_size = None
        try:
            while True:
                self._redraw()
                result = self._handle_key(self._read_key())
                if result is not _CONTINUE:
                    return result
        except KeyboardInterrupt:
            return None
        finally:
            self._con_stream.write(_LEAVE_SCREEN)
            self._con_stream.flush()
            if reader is not None:
                reader.close()
                self._read_key = None

    def _handle_key(self, key):
        if key is None or key == "resize":
            return _CONTINUE
        if self._too_small:
            if key == "ctrl+c" or self.keymap.get(key) in ("cancel", "quit"):
                return None
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
        return max(1, self._page_rows - 1)

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
