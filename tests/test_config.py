import os

from terminaltreeview import config as cfgmod
from terminaltreeview.config import Config, default_path, load, save, to_toml


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def codes(config):
    return [code for code, _ in config.warnings]


def test_defaults():
    config = Config()
    assert config.search.scope == "screen"
    assert config.search.recursive is False
    assert config.keys["go_inside"] == ["shift+enter"]
    assert config.keymap()["f2"] == "settings"


def test_missing_file_uses_defaults(tmp_path):
    config = load(str(tmp_path / "none.toml"))
    assert config.warnings == []
    assert config.path == str(tmp_path / "none.toml")
    assert config.search.scope == "screen"


def test_ttv_config_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("TTV_CONFIG", str(tmp_path / "custom.toml"))
    assert default_path() == str(tmp_path / "custom.toml")


def test_default_path_lives_in_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv("TTV_CONFIG", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert default_path() == os.path.join(str(tmp_path), "terminaltreeview", "config.toml")


def test_load_reads_values(tmp_path):
    path = write(tmp_path / "config.toml", """
[search]
scope = "folder"
recursive = true
max_depth = 3
match = "prefix"
skip = ["build"]

[files]
show_hidden = true

[layout]
max_items = 20
icons = "ascii"
help_bar = "compact"
theme = "mono"
language = "pt"
""")
    config = load(path)
    assert config.warnings == []
    assert config.search.scope == "folder"
    assert config.search.recursive is True
    assert config.search.max_depth == 3
    assert config.search.match == "prefix"
    assert config.search.skip == ["build"]
    assert config.files.show_hidden is True
    assert config.layout.icons == "ascii"
    assert config.layout.help_bar == "compact"
    assert config.layout.theme == "mono"
    assert config.layout.language == "pt"


def test_invalid_values_fall_back_with_warnings(tmp_path):
    path = write(tmp_path / "config.toml", """
[search]
scope = "everywhere"
max_depth = 0

[layout]
max_items = 500
show_path = "yes"
colour = "red"

[extra]
x = 1
""")
    config = load(path)
    assert config.search.scope == "screen"
    assert config.search.max_depth == 5
    assert config.layout.show_path is True
    assert codes(config).count("warn_invalid") == 3
    assert codes(config).count("warn_unknown") == 2


def test_keys_are_normalized_and_validated(tmp_path):
    path = write(tmp_path / "config.toml", """
[keys]
open = "Ctrl+P"
new_folder = ["q", "F7", "nonsense+x"]
settings = []
refresh = ["ctrl+p"]
teleport = ["f8"]
""")
    config = load(path)
    assert config.keys["open"] == ["ctrl+p"]
    assert config.keys["new_folder"] == ["f7"]
    assert config.keys["settings"] == ["f2"]
    assert config.keys["refresh"] == []
    assert config.keys["go_inside"] == ["shift+enter"]
    assert sorted(codes(config)) == sorted([
        "warn_unknown", "warn_reserved_key", "warn_bad_key", "warn_required_key", "warn_duplicate_key",
    ])


def test_explicit_keys_win_over_defaults(tmp_path):
    path = write(tmp_path / "config.toml", '[keys]\nopen = ["f5"]\n')
    config = load(path)
    assert config.keys["open"] == ["f5"]
    assert config.keys["refresh"] == []
    assert config.keymap()["f5"] == "open"


def test_quit_may_keep_ctrl_c(tmp_path):
    path = write(tmp_path / "config.toml", '[keys]\nquit = ["ctrl+c", "ctrl+q"]\nopen = ["ctrl+c"]\n')
    config = load(path)
    assert config.keys["quit"] == ["ctrl+c", "ctrl+q"]
    assert config.keys["open"] == []


def test_colors_are_validated(tmp_path):
    path = write(tmp_path / "config.toml", """
[colors]
selected = "bold magenta"
match = "not-a-color"
banana = "red"
""")
    config = load(path)
    assert config.colors == {"selected": "bold magenta"}
    assert sorted(codes(config)) == ["warn_bad_color", "warn_unknown"]


def test_syntax_error_uses_defaults_and_is_backed_up_on_save(tmp_path):
    path = write(tmp_path / "config.toml", "[search\nscope = 'folder'\n")
    config = load(path)
    assert config.broken
    assert codes(config) == ["warn_syntax"]
    assert config.search.scope == "screen"

    assert save(config)
    assert (tmp_path / "config.toml.bak").read_text(encoding="utf-8") == "[search\nscope = 'folder'\n"
    assert load(path).warnings == []


def test_save_round_trip(tmp_path):
    config = Config(path=str(tmp_path / "sub" / "config.toml"))
    config.search.scope = "folder"
    config.search.recursive = True
    config.search.max_depth = 7
    config.layout.language = "en"
    config.keys["open"] = ["f9", "ctrl+o"]
    config.colors = {"selected": "bold magenta"}
    assert save(config)

    loaded = load(config.path)
    assert loaded.warnings == []
    assert loaded.search.scope == "folder"
    assert loaded.search.recursive is True
    assert loaded.search.max_depth == 7
    assert loaded.keys["open"] == ["f9", "ctrl+o"]
    assert loaded.colors == {"selected": "bold magenta"}
    assert loaded.keys == config.keys


def test_saved_file_is_commented_in_the_chosen_language():
    config = Config()
    config.layout.language = "pt"
    assert "Onde a busca procura" in to_toml(config)
    config.layout.language = "en"
    text = to_toml(config)
    assert "Where the search looks" in text
    assert "press F2 inside ttv" in text


def test_save_without_path_does_nothing():
    assert save(Config()) is False


def test_reset_restores_everything():
    config = Config()
    config.search.scope = "folder"
    config.keys["open"] = []
    config.colors = {"selected": "red"}
    config.reset()
    assert config.search.scope == "screen"
    assert config.keys == cfgmod.default_keys()
    assert config.colors == {}
