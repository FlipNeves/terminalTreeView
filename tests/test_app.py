import os
import pytest
import sys
from unittest.mock import MagicMock
import msvcrt
from terminaltreeview.app import DirectoryNavigator, TreeNode

def test_navigator_initialization():
    nav = DirectoryNavigator()
    assert nav.root_dir == os.getcwd()
    assert nav.initial_root == os.getcwd()
    assert hasattr(nav, '_con_stream')
    assert not nav._con_stream.closed
    assert isinstance(nav.flat_list, list)
    assert isinstance(nav.expanded_dirs, set)

def test_navigator_lists_directories_and_files(tmp_path):
    (tmp_path / "dir_b").mkdir()
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "file_z.txt").touch()
    (tmp_path / "file_a.txt").touch()

    nav = DirectoryNavigator(root_dir=str(tmp_path))
    names = [node.name for node in nav.flat_list]
    assert names == ["dir_a", "dir_b", "file_a.txt", "file_z.txt"]

def test_navigator_hides_dot_dirs(tmp_path):
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible").mkdir()

    nav = DirectoryNavigator(root_dir=str(tmp_path))
    names = [node.name for node in nav.flat_list]
    assert "visible" in names
    assert ".hidden" not in names

def test_navigator_render_returns_text():
    from rich.text import Text
    nav = DirectoryNavigator()
    rendered = nav.render()
    assert isinstance(rendered, Text)
    assert "📂" in str(rendered)

def test_expand_directory(tmp_path):
    (tmp_path / "parent").mkdir()
    (tmp_path / "parent" / "child_dir").mkdir()
    (tmp_path / "parent" / "child_file.txt").touch()

    nav = DirectoryNavigator(root_dir=str(tmp_path))
    parent_idx = next(i for i, n in enumerate(nav.flat_list) if n.name == "parent")
    parent_node = nav.flat_list[parent_idx]
    
    assert not parent_node.is_expanded
    nav._toggle_expand(parent_node)
    
    names = [n.name for n in nav.flat_list]
    assert "child_dir" in names
    assert "child_file.txt" in names
    
    parent_node = nav.flat_list[parent_idx]
    assert parent_node.is_expanded

def test_collapse_directory(tmp_path):
    (tmp_path / "parent").mkdir()
    (tmp_path / "parent" / "child").mkdir()

    nav = DirectoryNavigator(root_dir=str(tmp_path))
    parent_idx = next(i for i, n in enumerate(nav.flat_list) if n.name == "parent")
    parent_node = nav.flat_list[parent_idx]

    nav._toggle_expand(parent_node)
    assert any(n.name == "child" for n in nav.flat_list)

    parent_node = nav.flat_list[parent_idx]
    nav._toggle_expand(parent_node)
    assert not any(n.name == "child" for n in nav.flat_list)

def test_navigate_up_resets_root(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()

    nav = DirectoryNavigator(root_dir=str(sub))
    assert nav.initial_root == str(sub)

    nav._navigate_up()
    assert nav.root_dir == str(tmp_path)

def test_selection_path(tmp_path):
    (tmp_path / "target_dir").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    
    idx = next(i for i, n in enumerate(nav.flat_list) if n.name == "target_dir")
    assert nav.flat_list[idx].path == str((tmp_path / "target_dir").resolve())

def test_navigator_expand_via_run(tmp_path, monkeypatch):
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "inner").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 0

    keys = iter([b'\r', b'q'])
    monkeypatch.setattr("msvcrt.getch", lambda: next(keys))
    nav.run()
    assert any(n.name == "inner" for n in nav.flat_list)

def test_ctrl_enter_exits_with_path(tmp_path, monkeypatch):
    (tmp_path / "target").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 0 

    monkeypatch.setattr("msvcrt.getch", lambda: b'\x0a')
    result = nav.run()
    assert result is not None
    assert result == str(tmp_path)

def test_shift_enter_exits_with_path(tmp_path, monkeypatch):
    (tmp_path / "target").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 0

    monkeypatch.setattr("msvcrt.getch", lambda: b'\r')
    mock_user32 = MagicMock()
    mock_user32.GetKeyState.return_value = 0x8000
    monkeypatch.setattr("terminaltreeview.app._user32", mock_user32)
    
    result = nav.run()
    assert result is not None
    assert result == str((tmp_path / "target").resolve())

def test_left_arrow_jumps_to_parent(tmp_path, monkeypatch):
    (tmp_path / "parent").mkdir()
    (tmp_path / "parent" / "child").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav._toggle_expand(nav.flat_list[0])
    nav.selected_index = 1
    
    keys = iter([b'\x00', b'K', b'q'])
    monkeypatch.setattr("msvcrt.getch", lambda: next(keys))
    nav.run()
    assert nav.selected_index == 0

def test_viewport_shows_all_when_fits(tmp_path):
    for i in range(5):
        (tmp_path / f"dir_{i}").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    viewport = nav._compute_viewport(30)
    assert viewport is None
    rendered = str(nav.render())
    assert "more..." not in rendered

def test_viewport_limits_output(tmp_path):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 0
    viewport = nav._compute_viewport(10)
    assert viewport is not None
    start, end = viewport
    assert end - start < 30
    assert start <= nav.selected_index < end

def test_viewport_scroll_indicators(tmp_path):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 15
    viewport = nav._compute_viewport(10)
    assert viewport is not None
    rendered = str(nav.render(viewport))
    assert "↑" in rendered
    assert "↓" in rendered
    assert "more..." in rendered

def test_viewport_follows_selection(tmp_path):
    for i in range(30):
        (tmp_path / f"dir_{i:02d}").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 2
    vp_top = nav._compute_viewport(10)
    assert vp_top is not None
    assert vp_top[0] <= 2 < vp_top[1]
    nav.selected_index = 28
    vp_bottom = nav._compute_viewport(10)
    assert vp_bottom is not None
    assert vp_bottom[0] <= 28 < vp_bottom[1]
    assert vp_top[0] != vp_bottom[0]

def test_get_visible_height(tmp_path):
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    height = nav._get_visible_height()
    assert isinstance(height, int)
    assert height > 0

def test_dynamic_breadcrumb_shows_selected_path(tmp_path):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 0
    rendered = str(nav.render())
    assert str(tmp_path / "alpha") in rendered
    nav.selected_index = 1
    rendered = str(nav.render())
    assert str(tmp_path / "beta") in rendered

def test_help_bar_is_rendered(tmp_path):
    (tmp_path / "folder").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    rendered = str(nav.render())
    assert "Navigate" in rendered
    assert "Expand" in rendered
    assert "Enter/→" in rendered
    assert "Ctrl+Enter" in rendered
    assert "Go Parent" in rendered
    assert "Shift+Enter" in rendered
    assert "Go Inside" in rendered
    assert "Quit" in rendered
