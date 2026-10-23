import json
import os
import shutil
from dataclasses import dataclass, field

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from terminaltreeview import keys as keymod
from terminaltreeview.i18n import Translator

SEARCH_SCOPES = ("screen", "folder")
MATCH_MODES = ("fuzzy", "contains", "prefix")
ICON_SETS = ("emoji", "ascii", "none")
HELP_BARS = ("full", "compact", "hidden")
THEMES = ("default", "vivid", "classic", "mono")
FOLDER_COLORS = ("theme", "files", "white", "blue", "cyan", "green", "yellow", "magenta")
LANGUAGE_CHOICES = ("auto", "pt", "en")

ACTIONS = (
    "up", "down", "page_up", "page_down", "first", "last", "expand", "back",
    "go_inside", "go_here", "open", "new_folder", "toggle_hidden", "refresh",
    "settings", "cancel", "quit",
)

DEFAULT_KEYS = {
    "up": ["up"],
    "down": ["down"],
    "page_up": ["pageup"],
    "page_down": ["pagedown"],
    "first": ["home"],
    "last": ["end"],
    "expand": ["enter", "right"],
    "back": ["left"],
    "go_inside": ["shift+enter"],
    "go_here": ["ctrl+enter"],
    "open": ["ctrl+o"],
    "new_folder": ["ctrl+n"],
    "toggle_hidden": ["ctrl+h", "alt+h"],
    "refresh": ["f5"],
    "settings": ["f2"],
    "cancel": ["esc"],
    "quit": ["ctrl+c"],
}

REQUIRED_ACTIONS = ("settings", "quit")

STYLE_NAMES = (
    "path", "root", "folder", "name", "selected", "match", "info", "note", "filter",
    "key", "hint", "error", "ok", "header", "value", "message", "border",
)

DEFAULT_SKIP = ("node_modules", ".git", "__pycache__", ".venv", "venv")


@dataclass(frozen=True)
class Option:
    section: str
    name: str
    kind: str
    choices: tuple = ()
    low: int = 0
    high: int = 0

    @property
    def id(self) -> str:
        return f"{self.section}.{self.name}"

    def accepts(self, value) -> bool:
        if self.kind == "bool":
            return isinstance(value, bool)
        if self.kind == "int":
            return isinstance(value, int) and not isinstance(value, bool) and self.low <= value <= self.high
        return value in self.choices


OPTIONS = (
    Option("search", "scope", "choice", SEARCH_SCOPES),
    Option("search", "recursive", "bool"),
    Option("search", "max_depth", "int", low=1, high=20),
    Option("search", "match", "choice", MATCH_MODES),
    Option("files", "show_hidden", "bool"),
    Option("files", "dirs_only", "bool"),
    Option("layout", "fullscreen", "bool"),
    Option("layout", "max_items", "int", low=3, high=50),
    Option("layout", "icons", "choice", ICON_SETS),
    Option("layout", "help_bar", "choice", HELP_BARS),
    Option("layout", "show_path", "bool"),
    Option("layout", "theme", "choice", THEMES),
    Option("layout", "folder_color", "choice", FOLDER_COLORS),
    Option("layout", "language", "choice", LANGUAGE_CHOICES),
)
OPTION_BY_ID = {option.id: option for option in OPTIONS}
SECTIONS = ("search", "files", "layout")


@dataclass
class SearchSettings:
    scope: str = "screen"
    recursive: bool = False
    max_depth: int = 5
    match: str = "fuzzy"
    skip: list = field(default_factory=lambda: list(DEFAULT_SKIP))


@dataclass
class FileSettings:
    show_hidden: bool = False
    dirs_only: bool = False


@dataclass
class LayoutSettings:
    fullscreen: bool = True
    max_items: int = 12
    icons: str = "emoji"
    help_bar: str = "full"
    show_path: bool = True
    theme: str = "default"
    folder_color: str = "theme"
    language: str = "auto"


def default_keys() -> dict[str, list[str]]:
    return {action: list(keys) for action, keys in DEFAULT_KEYS.items()}


@dataclass
class Config:
    search: SearchSettings = field(default_factory=SearchSettings)
    files: FileSettings = field(default_factory=FileSettings)
    layout: LayoutSettings = field(default_factory=LayoutSettings)
    keys: dict = field(default_factory=default_keys)
    colors: dict = field(default_factory=dict)
    path: str | None = None
    warnings: list = field(default_factory=list)
    broken: bool = False

    def get(self, option_id: str):
        section, name = option_id.split(".")
        return getattr(getattr(self, section), name)

    def set(self, option_id: str, value):
        section, name = option_id.split(".")
        setattr(getattr(self, section), name, value)

    def keymap(self) -> dict[str, str]:
        return {key: action for action in ACTIONS for key in self.keys.get(action, [])}

    def reset(self):
        fresh = Config()
        self.search, self.files, self.layout = fresh.search, fresh.files, fresh.layout
        self.keys, self.colors = fresh.keys, fresh.colors


def default_value(option_id: str):
    return Config().get(option_id)


def default_path() -> str:
    override = os.environ.get("TTV_CONFIG")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "terminaltreeview", "config.toml")


def _show(value) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, str) else repr(value)


def load(path: str | None = None) -> Config:
    config = Config(path=os.path.abspath(path) if path else default_path())
    try:
        with open(config.path, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return config
    except tomllib.TOMLDecodeError as error:
        config.broken = True
        config.warnings.append(("warn_syntax", {"error": str(error)}))
        return config
    except (OSError, UnicodeDecodeError) as error:
        config.warnings.append(("warn_read", {"error": getattr(error, "strerror", None) or str(error)}))
        return config
    _apply(config, data)
    return config


def _apply(config: Config, data: dict):
    warnings = config.warnings
    for name in data:
        if name not in SECTIONS + ("keys", "colors"):
            warnings.append(("warn_unknown", {"name": name}))
    for section in SECTIONS:
        table = data.get(section, {})
        if not isinstance(table, dict):
            warnings.append(("warn_invalid", {"name": section, "value": _show(table)}))
            continue
        for name, value in table.items():
            if section == "search" and name == "skip":
                if isinstance(value, list) and all(isinstance(item, str) for item in value):
                    config.search.skip = list(value)
                else:
                    warnings.append(("warn_invalid", {"name": "search.skip", "value": _show(value)}))
                continue
            option = OPTION_BY_ID.get(f"{section}.{name}")
            if option is None:
                warnings.append(("warn_unknown", {"name": f"{section}.{name}"}))
            elif option.accepts(value):
                config.set(option.id, value)
            else:
                warnings.append(("warn_invalid", {"name": option.id, "value": _show(value)}))
    config.keys = _parse_keys(data.get("keys", {}), warnings)
    config.colors = _parse_colors(data.get("colors", {}), warnings)


def _parse_keys(table, warnings: list) -> dict[str, list[str]]:
    if not isinstance(table, dict):
        warnings.append(("warn_invalid", {"name": "keys", "value": _show(table)}))
        table = {}
    for action in table:
        if action not in ACTIONS:
            warnings.append(("warn_unknown", {"name": f"keys.{action}"}))

    result: dict[str, list[str]] = {}
    owner: dict[str, str] = {}
    for action in ACTIONS:
        if action not in table:
            continue
        raw = table[action]
        items = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else None
        if items is None:
            warnings.append(("warn_invalid", {"name": f"keys.{action}", "value": _show(raw)}))
            continue
        chosen = []
        for item in items:
            key = keymod.normalize(item)
            if key is None:
                warnings.append(("warn_bad_key", {"action": action, "key": _show(item)}))
            elif keymod.is_reserved(key) and not (action == "quit" and key == "ctrl+c"):
                warnings.append(("warn_reserved_key", {"action": action, "key": keymod.display(key)}))
            elif key in owner:
                warnings.append(("warn_duplicate_key", {"action": action, "other": owner[key], "key": keymod.display(key)}))
            elif key not in chosen:
                chosen.append(key)
                owner[key] = action
        if not chosen and action in REQUIRED_ACTIONS:
            warnings.append(("warn_required_key", {"action": action}))
            continue
        result[action] = chosen

    for action in ACTIONS:
        if action not in result:
            result[action] = [key for key in DEFAULT_KEYS[action] if key not in owner]
            for key in result[action]:
                owner[key] = action
    return result


def _parse_colors(table, warnings: list) -> dict[str, str]:
    from rich.errors import StyleSyntaxError
    from rich.style import Style

    if not isinstance(table, dict):
        warnings.append(("warn_invalid", {"name": "colors", "value": _show(table)}))
        return {}
    colors = {}
    for name, value in table.items():
        if name not in STYLE_NAMES:
            warnings.append(("warn_unknown", {"name": f"colors.{name}"}))
            continue
        try:
            if not isinstance(value, str):
                raise StyleSyntaxError(value)
            Style.parse(value)
        except StyleSyntaxError:
            warnings.append(("warn_bad_color", {"name": name, "value": _show(value)}))
            continue
        colors[name] = value
    return colors


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return "[" + ", ".join(_toml_value(item) for item in value) + "]"


def _comment(lines: list[str], text: str):
    lines.extend(f"# {line}".rstrip() for line in text.splitlines())


def to_toml(config: Config) -> str:
    t = Translator(config.layout.language)
    settings_keys = config.keys.get("settings") or DEFAULT_KEYS["settings"]
    lines: list[str] = []
    _comment(lines, t("cfg_header", key=keymod.display(settings_keys[0])))
    for section in SECTIONS:
        lines.extend(["", f"[{section}]"])
        for option in OPTIONS:
            if option.section != section:
                continue
            _comment(lines, t(f"cfg_{option.id}"))
            lines.append(f"{option.name} = {_toml_value(config.get(option.id))}")
        if section == "search":
            _comment(lines, t("cfg_search.skip"))
            lines.append(f"skip = {_toml_value(config.search.skip)}")
    lines.extend(["", "[keys]"])
    _comment(lines, t("cfg_keys"))
    for action in ACTIONS:
        lines.append(f"{action} = {_toml_value(config.keys.get(action, []))}")
    lines.append("")
    if config.colors:
        lines.append("[colors]")
        lines.extend(f"{name} = {_toml_value(value)}" for name, value in config.colors.items())
    else:
        _comment(lines, t("cfg_colors"))
    return "\n".join(lines) + "\n"


def save(config: Config) -> bool:
    if not config.path:
        return False
    folder = os.path.dirname(config.path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    if config.broken and os.path.exists(config.path):
        shutil.copyfile(config.path, config.path + ".bak")
    temp = config.path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(to_toml(config))
    os.replace(temp, config.path)
    config.broken = False
    return True
