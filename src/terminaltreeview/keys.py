import ctypes
import ctypes.wintypes as wt
from collections import deque

KEY_EVENT = 0x0001
WINDOW_BUFFER_SIZE_EVENT = 0x0004

RIGHT_ALT_PRESSED = 0x0001
LEFT_ALT_PRESSED = 0x0002
RIGHT_CTRL_PRESSED = 0x0004
LEFT_CTRL_PRESSED = 0x0008
SHIFT_PRESSED = 0x0010

_ALT = RIGHT_ALT_PRESSED | LEFT_ALT_PRESSED
_CTRL = RIGHT_CTRL_PRESSED | LEFT_CTRL_PRESSED

_ENABLE_WINDOW_INPUT = 0x0008
_ENABLE_QUICK_EDIT_MODE = 0x0040
_ENABLE_EXTENDED_FLAGS = 0x0080

_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x1
_FILE_SHARE_WRITE = 0x2
_OPEN_EXISTING = 3
_INVALID_HANDLE = ctypes.c_void_p(-1).value

VK_SHIFT = 0x10
VK_MENU = 0x12

_VK_NAMES = {
    0x08: "backspace",
    0x09: "tab",
    0x0D: "enter",
    0x1B: "esc",
    0x20: "space",
    0x21: "pageup",
    0x22: "pagedown",
    0x23: "end",
    0x24: "home",
    0x25: "left",
    0x26: "up",
    0x27: "right",
    0x28: "down",
    0x2D: "insert",
    0x2E: "delete",
}
_VK_NAMES.update({0x70 + i: f"f{i + 1}" for i in range(12)})

_MODIFIER_VKS = frozenset({
    0x10, 0x11, 0x12, 0x14, 0x5B, 0x5C, 0x5D, 0x90, 0x91, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,
})

NAMED_KEYS = frozenset(_VK_NAMES.values())
MODIFIERS = ("ctrl", "alt", "shift")

_ALIASES = {
    "escape": "esc",
    "return": "enter",
    "del": "delete",
    "ins": "insert",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "page_up": "pageup",
    "page_down": "pagedown",
    "bksp": "backspace",
    "control": "ctrl",
    "↑": "up",
    "↓": "down",
    "←": "left",
    "→": "right",
}

_DISPLAY = {
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "enter": "Enter",
    "esc": "Esc",
    "tab": "Tab",
    "space": "Space",
    "backspace": "Backspace",
    "pageup": "PgUp",
    "pagedown": "PgDn",
    "home": "Home",
    "end": "End",
    "insert": "Ins",
    "delete": "Del",
}


def normalize(name) -> str | None:
    if not isinstance(name, str):
        return None
    parts = [part.strip().lower() for part in name.split("+")]
    if not all(parts):
        return None
    *mods, base = parts
    mods = [_ALIASES.get(mod, mod) for mod in mods]
    base = _ALIASES.get(base, base)
    if any(mod not in MODIFIERS for mod in mods) or len(set(mods)) != len(mods):
        return None
    if base not in NAMED_KEYS and not (len(base) == 1 and base.isascii() and base.isalnum()):
        return None
    return "+".join([mod for mod in MODIFIERS if mod in mods] + [base])


def is_reserved(key: str) -> bool:
    if key == "ctrl+c":
        return True
    *mods, base = key.split("+")
    if {"ctrl", "alt"} & set(mods):
        return False
    if base in ("backspace", "space"):
        return True
    return base not in NAMED_KEYS


def display(key: str) -> str:
    if len(key) == 1:
        return "Space" if key == " " else key.upper()
    *mods, base = key.split("+")
    return "+".join([mod.capitalize() for mod in mods] + [_DISPLAY.get(base, base.upper())])


def translate(key_down: bool, vk: int, char: str, state: int, shift_down=None) -> str | None:
    if char == "\x00":
        char = ""
    if not key_down:
        if vk == VK_MENU and char and char.isprintable():
            return char
        return None
    if vk in _MODIFIER_VKS:
        return None
    ctrl = bool(state & _CTRL)
    alt = bool(state & _ALT)
    shift = bool(state & SHIFT_PRESSED)
    if char and char.isprintable() and ctrl == alt:
        return char
    name = _VK_NAMES.get(vk)
    if name is None:
        if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
            name = chr(vk).lower()
        elif char in ("\r", "\n"):
            name = "enter"
        elif char == "\x1b":
            name = "esc"
        elif char == "\t":
            name = "tab"
        elif char in ("\x08", "\x7f"):
            name = "backspace"
        elif char and "\x01" <= char <= "\x1a":
            name, ctrl = chr(ord(char) + 0x60), True
        else:
            return None
    if name == "enter" and char == "\n":
        ctrl = True
    if name == "enter" and not (shift or ctrl or alt) and shift_down is not None and shift_down():
        shift = True
    mods = [mod for mod, active in (("ctrl", ctrl), ("alt", alt), ("shift", shift)) if active]
    return "+".join(mods + [name])


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wt.BOOL),
        ("wRepeatCount", wt.WORD),
        ("wVirtualKeyCode", wt.WORD),
        ("wVirtualScanCode", wt.WORD),
        ("UnicodeChar", wt.WCHAR),
        ("dwControlKeyState", wt.DWORD),
    ]


class _EVENT(ctypes.Union):
    _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("_raw", ctypes.c_byte * 16)]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wt.WORD), ("Event", _EVENT)]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateFileW.restype = wt.HANDLE
_kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
_kernel32.ReadConsoleInputW.argtypes = [wt.HANDLE, ctypes.POINTER(INPUT_RECORD), wt.DWORD, ctypes.POINTER(wt.DWORD)]
_kernel32.GetConsoleMode.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
_kernel32.SetConsoleMode.argtypes = [wt.HANDLE, wt.DWORD]
_kernel32.CloseHandle.argtypes = [wt.HANDLE]

try:
    _user32 = ctypes.WinDLL("user32")
except OSError:
    _user32 = None


def physical_shift_down() -> bool:
    if _user32 is None:
        return False
    try:
        return bool(_user32.GetKeyState(VK_SHIFT) & 0x8000)
    except OSError:
        return False


class ConsoleKeyReader:
    def __init__(self, shift_down=physical_shift_down):
        self._shift_down = shift_down
        self._handle = None
        self._saved_mode = None
        self._pending: deque[str] = deque()
        self._high_surrogate = ""

    def open(self):
        if self._handle is not None:
            return
        handle = _kernel32.CreateFileW(
            "CONIN$", _GENERIC_READ | _GENERIC_WRITE, _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            None, _OPEN_EXISTING, 0, None)
        if not handle or handle == _INVALID_HANDLE:
            raise OSError(ctypes.get_last_error(), "CONIN$")
        mode = wt.DWORD()
        if _kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            self._saved_mode = mode.value
            _kernel32.SetConsoleMode(
                handle, _ENABLE_EXTENDED_FLAGS | _ENABLE_WINDOW_INPUT | (mode.value & _ENABLE_QUICK_EDIT_MODE))
        self._handle = handle

    def close(self):
        if self._handle is None:
            return
        if self._saved_mode is not None:
            _kernel32.SetConsoleMode(self._handle, self._saved_mode)
        _kernel32.CloseHandle(self._handle)
        self._handle = None
        self._saved_mode = None

    def __call__(self) -> str:
        self.open()
        while not self._pending:
            record = INPUT_RECORD()
            count = wt.DWORD()
            if not _kernel32.ReadConsoleInputW(self._handle, ctypes.byref(record), 1, ctypes.byref(count)):
                raise OSError(ctypes.get_last_error(), "ReadConsoleInputW")
            if record.EventType == WINDOW_BUFFER_SIZE_EVENT:
                return "resize"
            if record.EventType != KEY_EVENT:
                continue
            event = record.Event.KeyEvent
            char = event.UnicodeChar
            if "\ud800" <= char <= "\udfff":
                if not event.bKeyDown:
                    continue
                if char <= "\udbff":
                    self._high_surrogate = char
                    continue
                if not self._high_surrogate:
                    continue
                char = (self._high_surrogate + char).encode("utf-16-le", "surrogatepass").decode("utf-16-le")
                self._high_surrogate = ""
            key = translate(bool(event.bKeyDown), event.wVirtualKeyCode, char,
                            event.dwControlKeyState, self._shift_down)
            if key:
                self._pending.extend([key] * max(1, event.wRepeatCount))
        return self._pending.popleft()
