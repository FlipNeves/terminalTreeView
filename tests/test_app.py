import ctypes
import io
import os

import pytest
from rich.text import Text

from terminaltreeview import app as app_module
from terminaltreeview import fs
from terminaltreeview.app import STYLES, DirectoryNavigator, compute_window
from terminaltreeview.i18n import Translator

FILE_ATTRIBUTE_HIDDEN = 0x2


def names(nodes):
    return [node.name for node in nodes]


def selected_name(nav):
    return nav.filtered_list[nav.selected_index].name


def test_navigator_initialization():
    nav = DirectoryNavigator()
    assert nav.root_dir == os.getcwd()
    assert nav.initial_root == os.getcwd()
    assert not nav._con_stream.closed
    assert isinstance(nav.flat_list, list)
    assert isinstance(nav.filtered_list, list)
    assert isinstance(nav.expanded_dirs, set)


def test_navigator_lists_directories_and_files(tmp_path, make_nav):
    (tmp_path / "dir_b").mkdir()
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "file_z.txt").touch()
    (tmp_path / "file_a.txt").touch()

    nav = make_nav(tmp_path)
    assert names(nav.flat_list) == ["dir_a", "dir_b", "file_a.txt", "file_z.txt"]


def test_navigator_hides_dot_dirs(tmp_path, make_nav):
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible").mkdir()

    nav = make_nav(tmp_path)
    assert names(nav.flat_list) == ["visible"]


def test_navigator_hides_windows_hidden_items(tmp_path, make_nav):
    (tmp_path / "visible").mkdir()
    secret = tmp_path / "secret"
    secret.mkdir()
    ctypes.windll.kernel32.SetFileAttributesW(str(secret), FILE_ATTRIBUTE_HIDDEN)

    nav = make_nav(tmp_path)
    assert names(nav.flat_list) == ["visible"]


def test_toggle_hidden_shows_hidden_items(tmp_path, make_nav):
    (tmp_path / ".git").mkdir()
    (tmp_path / "src").mkdir()

    nav = make_nav(tmp_path, keys=["ctrl+h", "ctrl+c"])
    nav.run()
    assert names(nav.flat_list) == [".git", "src"]
    assert nav.message is not None


def test_show_hidden_option(tmp_path, make_nav):
    (tmp_path / ".git").mkdir()
    nav = make_nav(tmp_path, files__show_hidden=True)
    assert names(nav.flat_list) == [".git"]


def test_dirs_only_hides_files(tmp_path, make_nav):
    (tmp_path / "folder").mkdir()
    (tmp_path / "file.txt").touch()

    nav = make_nav(tmp_path, files__dirs_only=True)
    assert names(nav.flat_list) == ["folder"]


def test_navigator_render_returns_text(make_nav):
    nav = make_nav(os.getcwd())
    rendered = nav.render()
    assert isinstance(rendered, Text)
    assert "📂" in str(rendered)


def test_files_use_document_icon(tmp_path, make_nav):
    (tmp_path / "notes.txt").touch()
    rendered = str(make_nav(tmp_path).render())
    assert "📄 notes.txt" in rendered
    assert "M⁺" not in rendered


def test_ascii_icons(tmp_path, make_nav):
    (tmp_path / "folder").mkdir()
    (tmp_path / "notes.txt").touch()
    rendered = str(make_nav(tmp_path, layout__icons="ascii").render())
    assert "+ folder\\" in rendered
    assert "📁" not in rendered and "📄" not in rendered


def test_show_path_can_be_disabled(tmp_path, make_nav):
    (tmp_path / "alpha").mkdir()
    rendered = str(make_nav(tmp_path, layout__show_path=False).render())
    assert str(tmp_path / "alpha") not in rendered


def test_default_theme_does_not_force_white_text():
    assert all("white" not in style for style in STYLES["default"].values())


def test_expand_directory(tmp_path, make_nav):
    (tmp_path / "parent").mkdir()
    (tmp_path / "parent" / "child_dir").mkdir()
    (tmp_path / "parent" / "child_file.txt").touch()

    nav = make_nav(tmp_path)
    parent_idx = next(i for i, n in enumerate(nav.flat_list) if n.name == "parent")
    parent_node = nav.flat_list[parent_idx]

    assert not parent_node.is_expanded
    nav._toggle_expand(parent_node)

    assert "child_dir" in names(nav.flat_list)
    assert "child_file.txt" in names(nav.flat_list)
    assert nav.flat_list[parent_idx].is_expanded


def test_collapse_directory(tmp_path, make_nav):
    (tmp_path / "parent").mkdir()
    (tmp_path / "parent" / "child").mkdir()

    nav = make_nav(tmp_path)
    nav._toggle_expand(nav.flat_list[0])
    assert "child" in names(nav.flat_list)

    nav._toggle_expand(nav.flat_list[0])
    assert "child" not in names(nav.flat_list)


def test_empty_folder_is_marked(tmp_path, make_nav):
    (tmp_path / "empty").mkdir()
    nav = make_nav(tmp_path)
    nav._toggle_expand(nav.flat_list[0])
    assert "(empty)" in str(nav.render())


def test_folder_with_only_hidden_items_is_marked(tmp_path, make_nav):
    (tmp_path / "box").mkdir()
    (tmp_path / "box" / ".secret").touch()
    nav = make_nav(tmp_path)
    nav._toggle_expand(nav.flat_list[0])
    assert "(only hidden items)" in str(nav.render())


def test_denied_folder_is_marked(tmp_path, make_nav, monkeypatch):
    locked = tmp_path / "locked"
    locked.mkdir()
    real_scandir = os.scandir

    def fake_scandir(path):
        if os.path.normcase(str(path)) == os.path.normcase(str(locked)):
            raise PermissionError(13, "Access is denied")
        return real_scandir(path)

    monkeypatch.setattr(fs.os, "scandir", fake_scandir)
    nav = make_nav(tmp_path)
    nav._toggle_expand(nav.flat_list[0])
    assert "(access denied)" in str(nav.render())


def test_navigate_up_resets_root(tmp_path, make_nav):
    sub = tmp_path / "sub"
    sub.mkdir()

    nav = make_nav(sub)
    assert nav.initial_root == str(sub)

    nav._navigate_up()
    assert nav.root_dir == str(tmp_path)


def test_navigate_up_selects_the_folder_you_came_from(tmp_path, make_nav):
    (tmp_path / "aaa").mkdir()
    (tmp_path / "zzz").mkdir()

    nav = make_nav(tmp_path / "zzz", keys=["left", "ctrl+c"])
    nav.run()
    assert nav.root_dir == str(tmp_path)
    assert selected_name(nav) == "zzz"


def test_selection_path(tmp_path, make_nav):
    (tmp_path / "target_dir").mkdir()
    nav = make_nav(tmp_path)

    idx = next(i for i, n in enumerate(nav.flat_list) if n.name == "target_dir")
    assert nav.flat_list[idx].path == str((tmp_path / "target_dir").resolve())


def test_navigator_expand_via_run(tmp_path, make_nav):
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "inner").mkdir()

    nav = make_nav(tmp_path, keys=["enter", "ctrl+c"])
    nav.run()
    assert "inner" in names(nav.flat_list)


def test_ctrl_enter_exits_with_path(tmp_path, make_nav):
    (tmp_path / "target").mkdir()
    nav = make_nav(tmp_path, keys=["ctrl+enter"])
    assert nav.run() == str(tmp_path)


def test_shift_enter_exits_with_path(tmp_path, make_nav):
    (tmp_path / "target").mkdir()
    nav = make_nav(tmp_path, keys=["shift+enter"])
    assert nav.run() == str((tmp_path / "target").resolve())


def test_escape_quits_without_path(tmp_path, make_nav):
    nav = make_nav(tmp_path, keys=["esc"])
    assert nav.run() is None


def test_left_arrow_jumps_to_parent(tmp_path, make_nav):
    (tmp_path / "parent").mkdir()
    (tmp_path / "parent" / "child").mkdir()
    nav = make_nav(tmp_path, keys=["left", "ctrl+c"])
    nav._toggle_expand(nav.flat_list[0])
    nav.selected_index = 1

    nav.run()
    assert nav.selected_index == 0


def test_page_home_and_end_keys(tmp_path, make_nav):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()

    nav = make_nav(tmp_path, keys=["end", "ctrl+c"])
    nav.run()
    assert nav.selected_index == 29

    nav = make_nav(tmp_path, keys=["pagedown", "pagedown", "ctrl+c"])
    nav.run()
    assert nav.selected_index == 2 * nav._page_size()

    nav = make_nav(tmp_path, keys=["end", "home", "ctrl+c"])
    nav.run()
    assert nav.selected_index == 0


def test_viewport_shows_all_when_fits(tmp_path, make_nav):
    for i in range(5):
        (tmp_path / f"dir_{i}").mkdir()
    nav = make_nav(tmp_path)
    assert nav._compute_viewport(30) is None
    assert "more..." not in str(nav.render())


def test_viewport_limits_output(tmp_path, make_nav):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = make_nav(tmp_path)
    nav.selected_index = 0
    viewport = nav._compute_viewport(10)
    assert viewport is not None
    start, end = viewport
    assert end - start < 30
    assert start <= nav.selected_index < end


def test_viewport_scroll_indicators(tmp_path, make_nav):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = make_nav(tmp_path)
    nav.selected_index = 15
    viewport = nav._compute_viewport(10)
    assert viewport is not None
    rendered = str(nav.render(viewport))
    assert "↑" in rendered
    assert "↓" in rendered
    assert "more..." in rendered


def test_viewport_follows_selection(tmp_path, make_nav):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = make_nav(tmp_path)
    nav.selected_index = 2
    vp_top = nav._compute_viewport(10)
    assert vp_top is not None
    assert vp_top[0] <= 2 < vp_top[1]
    nav.selected_index = 28
    vp_bottom = nav._compute_viewport(10)
    assert vp_bottom is not None
    assert vp_bottom[0] <= 28 < vp_bottom[1]
    assert vp_top[0] != vp_bottom[0]


def test_max_items_option_controls_viewport(tmp_path, make_nav):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = make_nav(tmp_path, layout__max_items=20)
    start, end = nav._compute_viewport(100)
    assert end - start + (start > 0) + (end < 30) <= 20
    assert end - start > 12


def test_compute_window_invariants():
    for total in range(1, 40):
        for budget in range(3, 15):
            for selected in range(total):
                window = compute_window(total, selected, budget)
                if window is None:
                    assert total <= budget
                    continue
                start, end = window
                assert 0 <= start <= selected < end <= total
                assert (end - start) + (start > 0) + (end < total) <= budget


def test_get_visible_height(tmp_path, make_nav):
    nav = make_nav(tmp_path)
    height = nav._get_visible_height()
    assert isinstance(height, int)
    assert height > 0


def test_dynamic_breadcrumb_shows_selected_path(tmp_path, make_nav):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    nav = make_nav(tmp_path)
    nav.selected_index = 0
    assert str(tmp_path / "alpha") in str(nav.render())
    nav.selected_index = 1
    assert str(tmp_path / "beta") in str(nav.render())


def test_help_bar_is_rendered(tmp_path, make_nav):
    (tmp_path / "folder").mkdir()
    rendered = str(make_nav(tmp_path).render())
    for text in ("Navigate", "Expand", "Enter/→", "Ctrl+Enter", "Go Here", "Shift+Enter",
                 "Go Inside", "Ctrl+O", "Open", "F2", "Settings", "Quit/Clear"):
        assert text in rendered


def test_help_bar_uses_configured_keys(tmp_path, make_nav):
    nav = make_nav(tmp_path)
    nav.config.keys["open"] = ["f9"]
    nav.apply_config("keys")
    rendered = str(nav.render())
    assert "F9 Open" in rendered
    assert "Ctrl+O" not in rendered


def test_help_bar_modes(tmp_path, make_nav):
    compact = str(make_nav(tmp_path, layout__help_bar="compact").render())
    assert "Go Inside" in compact
    assert "New Folder" not in compact
    hidden = str(make_nav(tmp_path, layout__help_bar="hidden").render())
    assert "Navigate" not in hidden


def test_help_bar_follows_language(tmp_path, make_nav):
    rendered = str(make_nav(tmp_path, layout__language="pt").render())
    assert "Navegar" in rendered
    assert "Sair/Limpar" in rendered


def test_filtering_hides_non_matches(tmp_path, make_nav):
    (tmp_path / "apple").mkdir()
    (tmp_path / "banana").mkdir()
    (tmp_path / "apricot").mkdir()

    nav = make_nav(tmp_path, keys=["b", "ctrl+c"])
    assert len(nav.flat_list) == 3
    nav.run()

    assert nav.filter_text == "b"
    assert names(nav.filtered_list) == ["banana"]
    assert nav.selected_index == 0


def test_fuzzy_filter_matches_subsequence(tmp_path, make_nav):
    (tmp_path / "test_app.py").touch()
    (tmp_path / "apple").mkdir()
    (tmp_path / "trash_panda.txt").touch()

    nav = make_nav(tmp_path, keys=["t", "s", "t", "ctrl+c"])
    nav.run()

    assert nav.filter_text == "tst"
    assert "test_app.py" in names(nav.filtered_list)
    assert "apple" not in names(nav.filtered_list)


def test_contains_mode_requires_contiguous_text(tmp_path, make_nav):
    (tmp_path / "test_app.py").touch()
    (tmp_path / "trash.txt").touch()
    nav = make_nav(tmp_path, keys=["t", "s", "t", "ctrl+c"], search__match="contains")
    nav.run()
    assert nav.filtered_list == []


def test_filter_with_no_matches_yields_empty_list(tmp_path, make_nav):
    (tmp_path / "apple").mkdir()

    nav = make_nav(tmp_path, keys=["z", "ctrl+c"])
    nav.run()

    assert nav.filter_text == "z"
    assert nav.filtered_list == []
    assert "(no matches)" in str(nav.render())


def test_filter_header_shows_count(tmp_path, make_nav):
    (tmp_path / "apple").mkdir()
    (tmp_path / "banana").mkdir()
    (tmp_path / "apricot").mkdir()

    nav = make_nav(tmp_path)
    nav.filter_text = "ap"
    nav._apply_filter()
    rendered = str(nav.render())
    assert "Filter: ap" in rendered
    assert "(2/3)" in rendered


def test_typing_accented_characters_filters(tmp_path, make_nav):
    (tmp_path / "relatórios").mkdir()
    (tmp_path / "planilhas").mkdir()

    nav = make_nav(tmp_path, keys=["ó", "ctrl+c"])
    nav.run()
    assert nav.filter_text == "ó"
    assert names(nav.filtered_list) == ["relatórios"]


def test_search_ignores_accents(tmp_path, make_nav):
    (tmp_path / "Configurações").mkdir()
    (tmp_path / "Downloads").mkdir()

    nav = make_nav(tmp_path, keys=list("configuracoes") + ["ctrl+c"])
    nav.run()
    assert names(nav.filtered_list) == ["Configurações"]


def test_best_match_is_preselected(tmp_path, make_nav):
    (tmp_path / "a_p_p_x").mkdir()
    (tmp_path / "app").mkdir()

    nav = make_nav(tmp_path, keys=["a", "p", "p", "ctrl+c"])
    nav.run()
    assert names(nav.filtered_list) == ["a_p_p_x", "app"]
    assert selected_name(nav) == "app"


def test_escape_clears_filter_and_keeps_selection(tmp_path, make_nav):
    for name in ["alpha", "beta", "gamma", "delta", "projeto_a", "projeto_b"]:
        (tmp_path / name).mkdir()

    nav = make_nav(tmp_path, keys=["p", "r", "o", "j", "down", "esc", "ctrl+c"])
    nav.run()
    assert nav.filter_text == ""
    assert selected_name(nav) == "projeto_b"


def test_backspace_clearing_filter_keeps_selection(tmp_path, make_nav):
    for name in ["alpha", "beta", "zulu"]:
        (tmp_path / name).mkdir()

    nav = make_nav(tmp_path, keys=["z", "backspace", "ctrl+c"])
    nav.run()
    assert nav.filter_text == ""
    assert selected_name(nav) == "zulu"


def test_left_with_filter_goes_to_the_real_parent(tmp_path, make_nav):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "bob" / "cat").mkdir(parents=True)

    nav = make_nav(tmp_path, keys=["a", "down", "left", "ctrl+c"])
    nav._toggle_expand(next(n for n in nav.flat_list if n.name == "bob"))
    nav.run()
    assert nav.filter_text == ""
    assert selected_name(nav) == "bob"


def test_expanding_while_filtering_keeps_cursor_on_folder(tmp_path, make_nav):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "target" / "inner").mkdir(parents=True)

    nav = make_nav(tmp_path, keys=["t", "a", "r", "enter", "ctrl+c"])
    nav.run()
    assert nav.filter_text == ""
    assert selected_name(nav) == "target"
    assert "inner" in names(nav.flat_list)


def test_search_results_show_their_folder(tmp_path, make_nav):
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "app.py").touch()

    nav = make_nav(tmp_path, keys=list("app") + ["ctrl+c"])
    nav._toggle_expand(next(n for n in nav.flat_list if n.name == "src"))
    nav._toggle_expand(next(n for n in nav.flat_list if n.name == "pkg"))
    nav.run()
    assert f"📄 app.py  {os.path.join('src', 'pkg')}" in str(nav.render())


def test_enter_on_a_file_result_shows_it_in_the_tree(tmp_path, make_nav):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.txt").touch()
    (tmp_path / "zeta").mkdir()

    nav = make_nav(tmp_path, keys=list("notes") + ["enter", "ctrl+c"])
    nav._toggle_expand(nav.flat_list[0])
    nav.run()
    assert nav.filter_text == ""
    assert selected_name(nav) == "notes.txt"
    assert names(nav.flat_list) == ["docs", "notes.txt", "zeta"]


def test_folder_scope_limits_search_to_selected_folder(tmp_path, make_nav):
    (tmp_path / "client_a" / "reports").mkdir(parents=True)
    (tmp_path / "client_b" / "reports").mkdir(parents=True)

    nav = make_nav(tmp_path, keys=["r", "e", "p", "ctrl+c"], search__scope="folder")
    for name in ("client_b", "client_a"):
        nav._toggle_expand(next(n for n in nav.flat_list if n.name == name))
    nav.run()
    assert [n.path for n in nav.filtered_list] == [str(tmp_path / "client_a" / "reports")]
    assert "in client_a" in str(nav.render())


def test_folder_scope_opens_a_collapsed_folder(tmp_path, make_nav):
    (tmp_path / "client_a" / "reports").mkdir(parents=True)
    (tmp_path / "reports_root").mkdir()

    nav = make_nav(tmp_path, keys=["r", "e", "p", "ctrl+c"], search__scope="folder")
    nav.run()
    assert str(tmp_path / "client_a") in nav.expanded_dirs
    assert names(nav.filtered_list) == ["reports"]


def test_screen_scope_searches_everything_visible(tmp_path, make_nav):
    (tmp_path / "client_a" / "reports").mkdir(parents=True)
    (tmp_path / "client_b" / "reports").mkdir(parents=True)

    nav = make_nav(tmp_path, keys=["r", "e", "p", "ctrl+c"])
    for name in ("client_b", "client_a"):
        nav._toggle_expand(next(n for n in nav.flat_list if n.name == name))
    nav.run()
    assert len(nav.filtered_list) == 2


def test_recursive_search_finds_closed_subfolders(tmp_path, make_nav):
    deep = tmp_path / "a" / "b" / "c" / "target"
    deep.mkdir(parents=True)

    nav = make_nav(tmp_path, keys=list("target") + ["ctrl+c"], search__recursive=True)
    nav.run()
    assert [n.path for n in nav.filtered_list] == [str(deep)]
    rendered = str(nav.render())
    assert os.path.join("a", "b", "c") in rendered
    assert "including subfolders" in rendered


def test_recursive_result_enter_reveals_it_in_the_tree(tmp_path, make_nav):
    deep = tmp_path / "a" / "b" / "target"
    (deep / "inside").mkdir(parents=True)

    nav = make_nav(tmp_path, keys=list("target") + ["enter", "ctrl+c"], search__recursive=True)
    nav.run()
    assert nav.filter_text == ""
    assert selected_name(nav) == "target"
    assert "inside" in names(nav.flat_list)


def test_recursive_shift_enter_goes_straight_into_the_result(tmp_path, make_nav):
    deep = tmp_path / "a" / "b" / "target"
    deep.mkdir(parents=True)
    nav = make_nav(tmp_path, keys=list("target") + ["shift+enter"], search__recursive=True)
    assert nav.run() == str(deep)


def test_recursive_search_respects_depth_and_skip_list(tmp_path, make_nav):
    (tmp_path / "a" / "b" / "c" / "deepest").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "inner_hit").mkdir(parents=True)

    nav = make_nav(tmp_path, keys=list("deepest") + ["ctrl+c"], search__recursive=True, search__max_depth=2)
    nav.run()
    assert nav.filtered_list == []

    nav = make_nav(tmp_path, keys=list("inner") + ["ctrl+c"], search__recursive=True)
    nav.run()
    assert nav.filtered_list == []


def test_recursive_search_in_selected_folder(tmp_path, make_nav):
    (tmp_path / "client_a" / "x" / "reports").mkdir(parents=True)
    (tmp_path / "client_b" / "x" / "reports").mkdir(parents=True)

    nav = make_nav(tmp_path, keys=list("rep") + ["ctrl+c"], search__scope="folder", search__recursive=True)
    nav.selected_index = 1
    nav.run()
    assert [n.path for n in nav.filtered_list] == [str(tmp_path / "client_b" / "x" / "reports")]


def test_ctrl_o_opens_item(tmp_path, make_nav, monkeypatch):
    (tmp_path / "item.txt").touch()
    opened = []
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)

    nav = make_nav(tmp_path, keys=["ctrl+o", "ctrl+c"])
    nav.run()
    assert opened == [str(tmp_path / "item.txt")]


def test_ctrl_o_asks_before_running_an_executable(tmp_path, make_nav, monkeypatch):
    (tmp_path / "setup.bat").touch()
    opened = []
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)

    nav = make_nav(tmp_path, keys=["ctrl+o", "ctrl+c"])
    nav.run()
    assert opened == []
    assert "setup.bat" in nav.message[0]

    nav = make_nav(tmp_path, keys=["ctrl+o", "ctrl+o", "ctrl+c"])
    nav.run()
    assert opened == [str(tmp_path / "setup.bat")]


def test_ctrl_o_reports_errors(tmp_path, make_nav, monkeypatch):
    (tmp_path / "item.txt").touch()

    def broken(path):
        raise OSError(2, "No application is associated")

    monkeypatch.setattr(os, "startfile", broken, raising=False)
    nav = make_nav(tmp_path, keys=["ctrl+o", "ctrl+c"])
    nav.run()
    assert nav.message[1] == "error"


def test_new_folder_accepts_accents(tmp_path, make_nav):
    keys = ["ctrl+n"] + list("Relatórios") + ["enter", "ctrl+c"]
    nav = make_nav(tmp_path, keys=keys)
    nav.run()
    assert (tmp_path / "Relatórios").is_dir()
    assert selected_name(nav) == "Relatórios"


def test_new_folder_inside_a_nested_folder_is_revealed(tmp_path, make_nav):
    (tmp_path / "a" / "b").mkdir(parents=True)
    nav = make_nav(tmp_path, keys=list("b") + ["ctrl+n", "n", "e", "w", "enter", "ctrl+c"], search__recursive=True)
    nav.run()
    assert (tmp_path / "a" / "b" / "new").is_dir()
    assert selected_name(nav) == "new"


def test_output_encoding_follows_console_code_page():
    assert app_module._output_encoding(850) == "cp850"
    assert app_module._output_encoding(65001) == "utf-8"
    assert app_module._output_encoding(0) == "utf-8"
    assert app_module._output_encoding(99999) == "utf-8"


class _FakeStdout(io.TextIOWrapper):
    def __init__(self):
        super().__init__(io.BytesIO(), encoding="cp1252")

    def isatty(self):
        return False


def test_emit_path_writes_in_console_code_page(monkeypatch):
    fake = _FakeStdout()
    monkeypatch.setattr(app_module.sys, "stdout", fake)
    monkeypatch.setattr(app_module, "_console_code_page", lambda: 850)

    assert app_module._emit_path("C:\\Área", Translator("en")) == 0
    assert fake.buffer.getvalue() == "C:\\Área\n".encode("cp850")


def test_emit_path_refuses_characters_the_console_cannot_carry(monkeypatch, capsys):
    fake = _FakeStdout()
    monkeypatch.setattr(app_module.sys, "stdout", fake)
    monkeypatch.setattr(app_module, "_console_code_page", lambda: 850)

    assert app_module._emit_path("C:\\日本", Translator("en")) == 1
    assert fake.buffer.getvalue() == b""
    assert "ttv-setup" in capsys.readouterr().err


def test_main_version_goes_to_stderr(capsys):
    with pytest.raises(SystemExit) as exit_info:
        app_module.main(["--version"])
    assert exit_info.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "terminaltreeview" in captured.err


def test_main_rejects_a_missing_folder(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("TTV_CONFIG", str(tmp_path / "config.toml"))
    assert app_module.main([str(tmp_path / "missing")]) == 1
    assert "missing" in capsys.readouterr().err


def test_main_starts_in_the_given_folder(tmp_path, monkeypatch):
    (tmp_path / "start" / "inner").mkdir(parents=True)
    monkeypatch.setenv("TTV_CONFIG", str(tmp_path / "config.toml"))
    started = {}

    def fake_run(self):
        started["root"] = self.root_dir
        return None

    monkeypatch.setattr(DirectoryNavigator, "run", fake_run)
    assert app_module.main([str(tmp_path / "start")]) == 0
    assert started["root"] == str(tmp_path / "start")
