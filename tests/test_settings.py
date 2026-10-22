import pytest

from terminaltreeview.config import Config, load


@pytest.fixture
def settings_nav(tmp_path, make_nav):
    (tmp_path / "root").mkdir()
    config = Config(path=str(tmp_path / "cfg" / "config.toml"))
    config.layout.language = "en"
    nav = make_nav(tmp_path / "root", config=config)
    nav._do("settings", "f2", None)
    return nav


def select(nav, kind, ref):
    nav.settings.index = nav.settings.find(kind, ref)
    return nav.settings


def test_f2_opens_settings_and_esc_returns(tmp_path, make_nav):
    nav = make_nav(tmp_path, keys=["f2", "ctrl+c"])
    nav.run()
    assert nav.mode == "settings"

    nav = make_nav(tmp_path, keys=["f2", "esc", "ctrl+c"])
    nav.run()
    assert nav.mode == "tree"


def test_settings_screen_lists_sections_options_and_keys(settings_nav):
    rendered = str(settings_nav.render())
    for text in ("Settings", "SEARCH", "FILES", "LAYOUT", "KEYS", "Search in", "Everything on screen",
                 "Open with the default app", "Ctrl+O", "Restore all defaults"):
        assert text in rendered
    assert settings_nav.config.path in rendered


def test_changing_scope_applies_and_saves(settings_nav):
    screen = select(settings_nav, "option", "search.scope")
    screen.handle("right")
    assert settings_nav.config.search.scope == "folder"
    assert load(settings_nav.config.path).search.scope == "folder"
    screen.handle("left")
    assert settings_nav.config.search.scope == "screen"


def test_numbers_are_clamped(settings_nav):
    screen = select(settings_nav, "option", "layout.max_items")
    for _ in range(60):
        screen.handle("right")
    assert settings_nav.config.layout.max_items == 50


def test_toggling_hidden_items_rebuilds_the_tree(tmp_path, settings_nav):
    (tmp_path / "root" / ".git").mkdir()
    screen = select(settings_nav, "option", "files.show_hidden")
    screen.handle("enter")
    assert [n.name for n in settings_nav.flat_list] == [".git"]


def test_language_switch_applies_immediately(settings_nav):
    screen = select(settings_nav, "option", "layout.language")
    screen.handle("left")
    assert settings_nav.config.layout.language == "pt"
    assert "Configurações" in str(settings_nav.render())


def test_rebinding_a_key_moves_it_from_another_action(settings_nav):
    screen = select(settings_nav, "key", "open")
    screen.handle("enter")
    assert screen.capture == "set"
    screen.handle("ctrl+n")
    keys = settings_nav.config.keys
    assert keys["open"] == ["ctrl+n"]
    assert keys["new_folder"] == []
    assert "Ctrl+N" in screen.message[0]
    assert settings_nav.keymap["ctrl+n"] == "open"
    assert load(settings_nav.config.path).keys["open"] == ["ctrl+n"]


def test_adding_a_second_key(settings_nav):
    screen = select(settings_nav, "key", "open")
    screen.handle("+")
    screen.handle("f9")
    assert settings_nav.config.keys["open"] == ["ctrl+o", "f9"]


def test_reserved_keys_are_rejected(settings_nav):
    screen = select(settings_nav, "key", "open")
    for key in ("q", "backspace", "ctrl+c"):
        screen.handle("enter")
        screen.handle(key)
        assert settings_nav.config.keys["open"] == ["ctrl+o"]
        assert screen.message[1] == "error"


def test_escape_cancels_capture(settings_nav):
    screen = select(settings_nav, "key", "open")
    screen.handle("enter")
    screen.handle("esc")
    assert screen.capture is None
    assert settings_nav.config.keys["open"] == ["ctrl+o"]
    assert settings_nav.mode == "settings"


def test_required_actions_keep_at_least_one_key(settings_nav):
    screen = select(settings_nav, "key", "settings")
    screen.handle("delete")
    assert settings_nav.config.keys["settings"] == ["f2"]

    screen = select(settings_nav, "key", "open")
    screen.handle("enter")
    screen.handle("f2")
    assert settings_nav.config.keys["settings"] == ["f2"]
    assert settings_nav.config.keys["open"] == ["ctrl+o"]


def test_clearing_and_restoring_keys(settings_nav):
    screen = select(settings_nav, "key", "new_folder")
    screen.handle("delete")
    assert settings_nav.config.keys["new_folder"] == []
    screen.handle("r")
    assert settings_nav.config.keys["new_folder"] == ["ctrl+n"]


def test_restore_option_default(settings_nav):
    screen = select(settings_nav, "option", "layout.icons")
    screen.handle("right")
    assert settings_nav.config.layout.icons != "emoji"
    screen.handle("r")
    assert settings_nav.config.layout.icons == "emoji"


def test_restore_all_needs_confirmation(settings_nav):
    settings_nav.config.search.scope = "folder"
    screen = select(settings_nav, "reset", None)
    screen.handle("enter")
    assert settings_nav.config.search.scope == "folder"
    screen.handle("enter")
    assert settings_nav.config.search.scope == "screen"


def test_navigation_skips_section_headers(settings_nav):
    screen = settings_nav.settings
    assert screen.rows[screen.index][0] != "header"
    for _ in range(len(screen.rows) * 2):
        screen.handle("down")
        assert screen.rows[screen.index][0] != "header"


def test_settings_viewport_keeps_selection_visible(settings_nav):
    screen = select(settings_nav, "key", "quit")
    start, end = settings_nav._compute_viewport(20)
    assert start <= screen.index < end
