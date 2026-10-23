import ctypes
import ctypes.wintypes as wt

import pytest

from terminaltreeview.keys import (
    INPUT_RECORD,
    KEY_EVENT,
    ConsoleKeyReader,
    display,
    is_reserved,
    normalize,
    translate,
)

SHIFT = 0x0010
LCTRL = 0x0008
LALT = 0x0002
RALT = 0x0001


@pytest.mark.parametrize("vk, char, state, expected", [
    (0x26, "\0", 0, "up"),
    (0x28, "\0", 0, "down"),
    (0x25, "\0", 0, "left"),
    (0x27, "\0", 0, "right"),
    (0x0D, "\r", 0, "enter"),
    (0x0D, "\r", SHIFT, "shift+enter"),
    (0x0D, "\n", LCTRL, "ctrl+enter"),
    (0x00, "\n", 0, "ctrl+enter"),
    (0x1B, "\x1b", 0, "esc"),
    (0x08, "\x08", 0, "backspace"),
    (0x48, "\x08", LCTRL, "ctrl+h"),
    (0x08, "\x7f", LCTRL, "ctrl+backspace"),
    (0x48, "h", LALT, "alt+h"),
    (0x48, "H", LALT | SHIFT, "alt+shift+h"),
    (0x43, "\x03", LCTRL, "ctrl+c"),
    (0x4E, "\x0e", LCTRL, "ctrl+n"),
    (0x4F, "\x0f", LCTRL, "ctrl+o"),
    (0x71, "\0", 0, "f2"),
    (0x74, "\0", SHIFT, "shift+f5"),
    (0x24, "\0", 0, "home"),
    (0x23, "\0", 0, "end"),
    (0x21, "\0", 0, "pageup"),
    (0x22, "\0", 0, "pagedown"),
    (0x2E, "\0", 0, "delete"),
    (0x09, "\t", SHIFT, "shift+tab"),
    (0xBA, "ç", 0, "ç"),
    (0x41, "Á", SHIFT, "Á"),
    (0x51, "/", RALT | LCTRL, "/"),
    (0x20, " ", 0, " "),
    (0x20, " ", LCTRL, "ctrl+space"),
])
def test_translate(vk, char, state, expected):
    assert translate(True, vk, char, state) == expected


def test_translate_ignores_key_up_and_lone_modifiers():
    assert translate(False, 0x41, "a", 0) is None
    assert translate(True, 0x10, "\0", SHIFT) is None
    assert translate(True, 0xA2, "\0", LCTRL) is None
    assert translate(True, 0xBA, "\0", 0) is None


def test_translate_reads_alt_numpad_character_on_key_up():
    assert translate(False, 0x12, "é", 0) == "é"


def test_translate_uses_physical_shift_as_fallback_for_enter():
    assert translate(True, 0x0D, "\r", 0, lambda: True) == "shift+enter"
    assert translate(True, 0x0D, "\r", 0, lambda: False) == "enter"
    assert translate(True, 0x26, "\0", 0, lambda: True) == "up"


@pytest.mark.parametrize("name, expected", [
    ("Ctrl+Shift+Enter", "ctrl+shift+enter"),
    ("shift+ctrl+x", "ctrl+shift+x"),
    ("PgDn", "pagedown"),
    ("Escape", "esc"),
    ("alt+H", "alt+h"),
    ("F12", "f12"),
    ("↑", "up"),
    ("hyper+x", None),
    ("ctrl+", None),
    ("", None),
    ("ctrl+ctrl+x", None),
    ("f13", None),
    ("ctrl+ç", None),
    (42, None),
])
def test_normalize(name, expected):
    assert normalize(name) == expected


@pytest.mark.parametrize("key, expected", [
    ("ctrl+enter", "Ctrl+Enter"),
    ("up", "↑"),
    ("f2", "F2"),
    ("pagedown", "PgDn"),
    ("alt+shift+h", "Alt+Shift+H"),
    ("q", "Q"),
    (" ", "Space"),
])
def test_display(key, expected):
    assert display(key) == expected


@pytest.mark.parametrize("key, reserved", [
    ("a", True),
    ("shift+a", True),
    ("5", True),
    ("backspace", True),
    ("space", True),
    ("ctrl+c", True),
    ("ctrl+a", False),
    ("alt+a", False),
    ("f5", False),
    ("tab", False),
    ("shift+enter", False),
    ("ctrl+backspace", False),
])
def test_is_reserved(key, reserved):
    assert is_reserved(key) is reserved


def _record(char, vk=0, state=0, down=True, repeat=1):
    record = INPUT_RECORD()
    record.EventType = KEY_EVENT
    event = record.Event.KeyEvent
    event.bKeyDown = down
    event.wRepeatCount = repeat
    event.wVirtualKeyCode = vk
    event.UnicodeChar = char
    event.dwControlKeyState = state
    return record


def test_console_reader_reads_injected_events():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wt.HANDLE
    k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
    k32.GetConsoleMode.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
    k32.FlushConsoleInputBuffer.argtypes = [wt.HANDLE]
    k32.WriteConsoleInputW.argtypes = [wt.HANDLE, ctypes.POINTER(INPUT_RECORD), wt.DWORD, ctypes.POINTER(wt.DWORD)]
    k32.CloseHandle.argtypes = [wt.HANDLE]

    handle = k32.CreateFileW("CONIN$", 0xC0000000, 0x3, None, 3, 0, None)
    if not handle or handle == ctypes.c_void_p(-1).value:
        pytest.skip("no console input available")
    try:
        mode = wt.DWORD()
        if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
            pytest.skip("CONIN$ is not a console")
        records = [
            _record("ç", 0xBA),
            _record("ç", 0xBA, down=False),
            _record("\r", 0x0D, SHIFT),
            _record("\x08", 0x48, LCTRL),
            _record("\0", 0x71),
            _record("\ud83d", 0xE7),
            _record("\ude00", 0xE7),
            _record("x", 0x58, repeat=3),
        ]
        array = (INPUT_RECORD * len(records))(*records)
        written = wt.DWORD()
        k32.FlushConsoleInputBuffer(handle)
        assert k32.WriteConsoleInputW(handle, array, len(records), ctypes.byref(written))

        reader = ConsoleKeyReader(shift_down=lambda: False)
        try:
            keys = [reader() for _ in range(8)]
        finally:
            reader.close()

        restored = wt.DWORD()
        k32.GetConsoleMode(handle, ctypes.byref(restored))
        assert keys == ["ç", "shift+enter", "ctrl+h", "f2", "😀", "x", "x", "x"]
        assert restored.value == mode.value
    finally:
        k32.CloseHandle(handle)
