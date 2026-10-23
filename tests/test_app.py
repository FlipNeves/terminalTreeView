import ctypes
import io
import os

import pytest
from rich.cells import cell_len
from rich.text import Text

from terminaltreeview import app as app_module
from terminaltreeview import fs
from terminaltreeview.app import STYLES, DirectoryNavigator, build_styles, clip_start, compute_window
from terminaltreeview.config import STYLE_NAMES, THEMES
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
    assert "│" not in rendered and "╭" not in rendered and "|" in rendered


def test_show_path_can_be_disabled(tmp_path, make_nav):
    (tmp_path / "alpha").mkdir()
    rendered = str(make_nav(tmp_path, layout__show_path=False).render())
    assert str(tmp_path / "alpha") not in rendered


def test_default_theme_only_forces_white_on_folder_names():
    assert "white" in STYLES["default"]["folder"]
    assert all("white" not in style for name, style in STYLES["default"].items() if name != "folder")


def test_every_theme_styles_every_element():
    for theme in THEMES:
        assert set(STYLES[theme]) == set(STYLE_NAMES)


def test_folders_have_their_own_color_and_selection_only_colors_the_text(tmp_path, make_nav):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "notes.txt").touch()
    nav = make_nav(tmp_path)
    lines = nav._frame_lines(60, 20)[1:]
    selected = next(line for line in lines if "alpha" in line.plain)
    marked = "".join(selected.plain[span.start:span.end] for span in selected.spans
                     if span.style == nav.styles["selected"])
    assert marked.strip() == "▶ alpha"

    nav.selected_index = 1
    lines = nav._frame_lines(60, 20)[1:]
    folder = next(line for line in lines if "alpha" in line.plain)
    assert any(span.style == nav.styles["folder"] for span in folder.spans)
    assert all(span.style != nav.styles["selected"] for span in folder.spans)
    unstyled = next(line for line in lines if "notes.txt" in line.plain and "📄" in line.plain)
    assert unstyled.style == ""
    assert all(set(unstyled.plain[span.start:span.end]) <= {"│", " "} for span in unstyled.spans
               if span.style == nav.styles["border"])


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

    nav = make_nav(tmp_path, keys=["pagedown", "ctrl+c"])
    nav._get_window_size = lambda: (80, 14)
    nav.render()
    first_page = nav._page_rows
    nav.run()
    assert 1 < first_page < 30
    assert nav.selected_index == first_page - 1

    nav = make_nav(tmp_path, keys=["end", "home", "ctrl+c"])
    nav.run()
    assert nav.selected_index == 0


def test_list_shows_everything_when_it_fits(tmp_path, make_nav):
    for i in range(5):
        (tmp_path / f"dir_{i}").mkdir()
    rendered = str(make_nav(tmp_path).render(80, 30))
    assert "more..." not in rendered
    assert all(f"dir_{i}" in rendered for i in range(5))


def test_list_scrolls_with_the_selection(tmp_path, make_nav):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = make_nav(tmp_path, layout__show_path=False)
    nav.selected_index = 2
    top = str(nav.render(80, 14))
    assert "dir_02" in top and "dir_28" not in top
    assert top.count("more...") == 1
    nav.selected_index = 15
    middle = str(nav.render(80, 14))
    assert "dir_15" in middle and middle.count("more...") == 2
    nav.selected_index = 28
    bottom = str(nav.render(80, 14))
    assert "dir_28" in bottom and "dir_02" not in bottom
    assert bottom.count("more...") == 1


def test_list_grows_with_the_window(tmp_path, make_nav):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = make_nav(tmp_path, layout__show_path=False)
    small = str(nav.render(80, 14)).count("dir_")
    large = str(nav.render(80, 30)).count("dir_")
    assert 1 < small < large


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


def test_get_window_size(tmp_path, make_nav):
    nav = make_nav(tmp_path)
    width, height = DirectoryNavigator._get_window_size(nav)
    assert width > 0 and height > 0


def test_clip_start_keeps_the_end_of_the_path():
    assert clip_start("C:\\short", 20) == "C:\\short"
    clipped = clip_start("C:\\Users\\someone\\projects\\deep\\folder", 20)
    assert clipped.startswith("…") and clipped.endswith("\\deep\\folder")
    assert cell_len(clipped) == 20
    assert cell_len(clip_start("C:\\日本語\\日本語\\日本語", 9)) <= 9


def test_long_path_is_clipped_in_the_top_border(tmp_path, make_nav):
    (tmp_path / ("a" * 80)).mkdir()
    top = str(make_nav(tmp_path).render(60, 20)).split("\n")[0]
    assert cell_len(top) == 60
    assert top.startswith("╭─ …") and top.endswith(" ─╮")
    assert "a" * 20 in top


def frame(nav, width, height):
    return str(nav.render(width, height)).split("\n")


def assert_fills(lines, width, height):
    assert len(lines) == height
    assert all(cell_len(line) == width for line in lines)


@pytest.mark.parametrize("width, height", [(50, 14), (64, 20), (120, 40)])
def test_frame_fills_the_window_exactly(tmp_path, make_nav, width, height):
    for i in range(30):
        (tmp_path / f"folder_with_a_name_longer_than_the_window_{i:02d}").mkdir()
    nav = make_nav(tmp_path)
    nav.selected_index = 12
    nav.message = ("a long message that will not fit on a single line " * 4, "info")
    lines = frame(nav, width, height)
    assert_fills(lines, width, height)
    assert lines[0].startswith("╭─") and lines[-1].startswith("╰─") and lines[-1].endswith("╯")
    assert any("folder_with_a_name" in line for line in lines[1:])


def test_frame_fills_the_window_while_searching_and_creating(tmp_path, make_nav):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = make_nav(tmp_path)
    nav._type("d")
    assert_fills(frame(nav, 50, 14), 50, 14)
    nav._end_search()
    nav._begin_create()
    nav.new_folder_name = "x" * 80
    lines = frame(nav, 50, 14)
    assert_fills(lines, 50, 14)
    assert any(line.rstrip(" │").endswith("x█") for line in lines)


def test_folder_color_option(tmp_path, make_nav):
    assert build_styles("default", {}, "theme")["folder"] == STYLES["default"]["folder"]
    assert build_styles("default", {}, "green")["folder"] == "bold bright_green"
    assert build_styles("classic", {}, "files")["folder"] == STYLES["classic"]["name"]
    assert build_styles("default", {"folder": "red"}, "green")["folder"] == "red"
    assert make_nav(tmp_path, layout__folder_color="cyan").styles["folder"] == "bold bright_cyan"


def test_inline_frame_is_as_tall_as_its_content(tmp_path, make_nav):
    for i in range(5):
        (tmp_path / f"dir_{i}").mkdir()
    nav = make_nav(tmp_path, layout__fullscreen=False)
    lines = frame(nav, 80, 40)
    assert len(lines) == 2 + 1 + 5 + 1 + len(nav._tree_footer(76))
    assert all(cell_len(line) == 80 for line in lines)


def test_inline_list_is_limited_by_max_items_and_the_window(tmp_path, make_nav):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = make_nav(tmp_path, layout__fullscreen=False, layout__max_items=8, layout__show_path=False)
    lines = frame(nav, 80, 40)
    assert 1 < sum("dir_" in line for line in lines) <= 8
    assert len(lines) < 20
    assert len(frame(nav, 80, 14)) <= 13


def test_switching_between_full_screen_and_inline_drawing(tmp_path, make_nav):
    (tmp_path / "alpha").mkdir()
    nav = make_nav(tmp_path)
    nav._con_stream = io.StringIO()
    nav._redraw()
    assert nav._con_stream.getvalue().startswith("\x1b[?1049h\x1b[2J")

    nav.config.layout.fullscreen = False
    nav._con_stream = io.StringIO()
    nav._redraw()
    output = nav._con_stream.getvalue()
    rows = nav._inline_rows
    assert output.startswith("\x1b[?1049l") and output.count("\r\n") == rows - 1

    nav._con_stream = io.StringIO()
    nav._redraw()
    assert nav._con_stream.getvalue().startswith(f"\r\x1b[{rows - 1}A\x1b[J")
    assert nav._stop_mode() == f"\r\x1b[{rows - 1}A\x1b[J"


def test_inline_mode_never_uses_the_alternate_screen(tmp_path, make_nav):
    (tmp_path / "alpha").mkdir()
    nav = make_nav(tmp_path, keys=["down", "shift+enter"], layout__fullscreen=False)
    nav._con_stream = io.StringIO()
    assert nav.run() == str(tmp_path / "alpha")
    output = nav._con_stream.getvalue()
    assert "\x1b[?1049" not in output
    assert output.endswith("\x1b[J\x1b[?7h\x1b[?25h")


def test_too_small_window_shows_a_notice_and_only_quits(tmp_path, make_nav):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    nav = make_nav(tmp_path, keys=["down", "a", "ctrl+n", "f2", "esc"])
    nav._get_window_size = lambda: (40, 10)
    assert nav.run() is None
    assert nav.selected_index == 0 and nav.filter_text == ""
    assert not nav.creating and nav.mode == "tree"
    lines = frame(nav, 40, 10)
    assert_fills(lines, 40, 10)
    text = "\n".join(lines)
    assert "Window too small" in text and "50×14" in text and "40×10" in text


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


def hint_lines(nav, width):
    return [text.plain for text in nav._hint_texts(nav._help_groups(), width)]


def test_help_bar_follows_the_group_order_on_one_line(tmp_path, make_nav):
    lines = hint_lines(make_nav(tmp_path), 196)
    assert len(lines) == 1
    order = ["Navigate", "Expand", "Back", "Go Here", "Go Inside", "Open", "New Folder", "Hidden", "Settings",
             "Quit/Clear"]
    positions = [lines[0].index(label) for label in order]
    assert positions == sorted(positions)
    assert lines[0].count("│") == 3


def test_help_bar_breaks_lines_between_groups(tmp_path, make_nav):
    lines = hint_lines(make_nav(tmp_path), 46)

    def line_of(label):
        return next(i for i, line in enumerate(lines) if label in line)

    assert line_of("Navigate") == line_of("Expand") == line_of("Back")
    assert line_of("Go Here") == line_of("Go Inside")
    assert line_of("Open") == line_of("New Folder")
    assert line_of("Hidden") == line_of("Settings") == line_of("Quit/Clear")
    assert line_of("Navigate") < line_of("Go Here") < line_of("Open") < line_of("Hidden")
    assert all(cell_len(line) <= 46 for line in lines)


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
