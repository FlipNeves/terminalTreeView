from rich.cells import cell_len
from rich.text import Text

from terminaltreeview import config as cfgmod
from terminaltreeview import keys as keymod
from terminaltreeview.layout import clip_start, compute_window, list_rows


class SettingsScreen:
    def __init__(self, nav):
        self.nav = nav
        self.rows = self._build_rows()
        self.index = self._step(-1, 1)
        self.capture: str | None = None
        self.message: tuple[str, str] | None = None
        self._reset_armed = False

    @staticmethod
    def _build_rows() -> list[tuple[str, object]]:
        rows: list[tuple[str, object]] = []
        for section in cfgmod.SECTIONS:
            rows.append(("header", section))
            rows.extend(("option", option) for option in cfgmod.OPTIONS if option.section == section)
        rows.append(("header", "keys"))
        rows.extend(("key", action) for action in cfgmod.ACTIONS)
        rows.append(("reset", None))
        return rows

    def find(self, kind: str, ref) -> int:
        for i, row in enumerate(self.rows):
            if row[0] == kind and (row[1] == ref or getattr(row[1], "id", None) == ref):
                return i
        raise KeyError(ref)

    def _step(self, start: int, direction: int) -> int:
        index = start
        for _ in range(len(self.rows)):
            index = (index + direction) % len(self.rows)
            if self.rows[index][0] != "header":
                return index
        return 0

    def handle(self, key: str) -> str:
        config = self.nav.config
        armed, self._reset_armed = self._reset_armed, False
        if key == "resize":
            self._reset_armed = armed
            return "stay"
        self.message = None
        if self.capture:
            self._finish_capture(key)
            return "stay"
        if key == "ctrl+c" or key in config.keys.get("quit", []):
            return "quit"
        if key == "esc" or key in config.keys.get("settings", []):
            return "close"

        kind, ref = self.rows[self.index]
        if key in ("up", "shift+tab") or key in config.keys.get("up", []):
            self.index = self._step(self.index, -1)
        elif key in ("down", "tab") or key in config.keys.get("down", []):
            self.index = self._step(self.index, 1)
        elif key in ("pageup", "pagedown"):
            direction = -1 if key == "pageup" else 1
            for _ in range(5):
                self.index = self._step(self.index, direction)
        elif key == "home":
            self.index = self._step(-1, 1)
        elif key == "end":
            self.index = self._step(len(self.rows), -1)
        elif kind == "option":
            if key in ("right", "enter", " "):
                self._change(ref, 1)
            elif key == "left":
                self._change(ref, -1)
            elif key in ("r", "R"):
                self._restore_option(ref)
        elif kind == "key":
            if key == "enter":
                self.capture = "set"
            elif key in ("+", "insert"):
                self.capture = "add"
            elif key in ("delete", "backspace"):
                self._clear_keys(ref)
            elif key in ("r", "R"):
                self._restore_keys(ref)
        elif kind == "reset" and key == "enter":
            if armed:
                self.nav.config.reset()
                self._commit("reset", self.nav.t("reset_done"))
            else:
                self._reset_armed = True
                self.message = (self.nav.t("confirm_reset"), "message")
        return "stay"

    def _action_label(self, action: str) -> str:
        return self.nav.t(f"action_{action}")

    def _commit(self, changed: str, note: str | None = None):
        self.nav.apply_config(changed)
        try:
            saved = cfgmod.save(self.nav.config)
        except OSError as error:
            self.message = (self.nav.t("save_failed", error=error.strerror or str(error)), "error")
            return
        if note:
            self.message = (note, "message")
        elif saved:
            self.message = (self.nav.t("saved"), "ok")

    def _change(self, option: cfgmod.Option, step: int):
        config = self.nav.config
        value = config.get(option.id)
        if option.kind == "bool":
            new = not value
        elif option.kind == "int":
            new = min(option.high, max(option.low, value + step))
        else:
            choices = option.choices
            new = choices[(choices.index(value) + step) % len(choices)] if value in choices else choices[0]
        if new != value:
            config.set(option.id, new)
            self._commit(option.id)

    def _restore_option(self, option: cfgmod.Option):
        default = cfgmod.default_value(option.id)
        if self.nav.config.get(option.id) != default:
            self.nav.config.set(option.id, default)
            self._commit(option.id)

    def _take_key(self, key: str, action: str, notes: list[str]) -> bool:
        for other, bound in self.nav.config.keys.items():
            if other == action or key not in bound:
                continue
            if other in cfgmod.REQUIRED_ACTIONS and len(bound) == 1:
                self.message = (self.nav.t("key_required", action=self._action_label(other)), "error")
                return False
            bound.remove(key)
            notes.append(self.nav.t("key_moved", key=keymod.display(key), action=self._action_label(other)))
        return True

    def _finish_capture(self, key: str):
        if key == "resize":
            return
        mode, self.capture = self.capture, None
        action = self.rows[self.index][1]
        t = self.nav.t
        if key == "esc":
            return
        if key == "ctrl+c" and action != "quit":
            self.message = (t("key_reserved_quit"), "error")
            return
        if len(key) == 1 or (keymod.is_reserved(key) and key != "ctrl+c"):
            self.message = (t("key_reserved", key=keymod.display(key)), "error")
            return
        notes: list[str] = []
        if not self._take_key(key, action, notes):
            return
        bound = self.nav.config.keys.setdefault(action, [])
        if mode == "add":
            if key not in bound:
                bound.append(key)
        else:
            self.nav.config.keys[action] = [key]
        self._commit("keys", " ".join(notes) or None)

    def _clear_keys(self, action: str):
        if action in cfgmod.REQUIRED_ACTIONS:
            self.message = (self.nav.t("key_required", action=self._action_label(action)), "error")
            return
        if self.nav.config.keys.get(action):
            self.nav.config.keys[action] = []
            self._commit("keys")

    def _restore_keys(self, action: str):
        notes: list[str] = []
        wanted = []
        for key in cfgmod.DEFAULT_KEYS[action]:
            if self._take_key(key, action, notes):
                wanted.append(key)
            else:
                self.message = None
        self.nav.config.keys[action] = wanted
        self._commit("keys", " ".join(notes) or None)

    def _label(self, kind: str, ref) -> str:
        t = self.nav.t
        if kind == "option":
            return t(f"option_{ref.id}")
        if kind == "key":
            return self._action_label(ref)
        return t("reset_all")

    def _value(self, kind: str, ref) -> str:
        t = self.nav.t
        if kind == "key":
            bound = self.nav.config.keys.get(ref, [])
            return ", ".join(keymod.display(key) for key in bound) or t("no_key")
        value = self.nav.config.get(ref.id)
        if ref.kind == "bool":
            return t("yes") if value else t("no")
        if ref.kind == "int":
            return str(value)
        return t(f"value_{ref.id}.{value}")

    def _hints(self) -> list[list[tuple[str, str]]]:
        t = self.nav.t
        if self.capture:
            return [[("Esc", t("hint_cancel"))]]
        kind = self.rows[self.index][0]
        hints = [[("↑↓", t("help_navigate"))]]
        if kind == "option":
            hints.append([("←→", t("settings_change")), ("R", t("settings_default"))])
        elif kind == "key":
            hints.append([("Enter", t("settings_set_key")), ("+", t("settings_add_key")),
                          ("Del", t("settings_clear_key")), ("R", t("settings_default"))])
        elif kind == "reset":
            hints.append([("Enter", t("settings_confirm"))])
        hints.append([("Esc", t("settings_back"))])
        return hints

    def screen(self, width: int, height: int) -> tuple[str, list[Text], list[Text]]:
        nav, t, styles = self.nav, self.nav.t, self.nav.styles
        footer = []
        if self.capture:
            prompt = "capture_add" if self.capture == "add" else "capture_set"
            footer.append(Text(t(prompt, action=self._action_label(self.rows[self.index][1])),
                               style=styles["message"]))
        elif self.message:
            footer += nav._message_lines(self.message, width)
        footer += nav._hint_texts(self._hints(), width)

        body = []
        if nav.config.path:
            body.append(Text(clip_start(nav.config.path, width), style=styles["path"]))
        window = compute_window(len(self.rows), self.index, list_rows(height, len(body), footer))
        start, end = window if window is not None else (0, len(self.rows))
        if start > 0:
            body.append(Text("  " + t("more_above", n=start), style=styles["info"]))
        label_width = max(cell_len(self._label(kind, ref)) for kind, ref in self.rows if kind in ("option", "key"))
        for i in range(start, end):
            kind, ref = self.rows[i]
            if kind == "header":
                body.append(Text(f"  {t('section_' + ref).upper()}", style=styles["header"]))
                continue
            selected = i == self.index
            style = styles["selected"] if selected else styles["name"]
            label = self._label(kind, ref)
            line = Text()
            line.append("› " if selected else "  ", style=style)
            line.append(label, style=style)
            if kind != "reset":
                line.append(" " * (label_width - cell_len(label) + 2))
                value = self._value(kind, ref)
                if selected and kind == "option":
                    value = f"‹ {value} ›"
                line.append(value, style=style if selected else styles["value"])
            body.append(line)
        if end < len(self.rows):
            body.append(Text("  " + t("more_below", n=len(self.rows) - end), style=styles["info"]))
        return f"⚙ {t('settings_title')}", body, footer
