import os
import pytest
import sys
from unittest.mock import MagicMock

# Mock msvcrt for tests
import msvcrt
from terminaltreeview.app import DirectoryNavigator, TreeNode


def test_navigator_initialization():
    """Verify that the DirectoryNavigator can be initialized."""
    nav = DirectoryNavigator()
    assert nav.root_dir == os.getcwd()
    assert nav.initial_root == os.getcwd()
    assert hasattr(nav, '_con_stream')
    assert not nav._con_stream.closed
    assert isinstance(nav.flat_list, list)
    assert isinstance(nav.expanded_dirs, set)


def test_navigator_lists_directories_and_files(tmp_path):
    """Verify that both directories and files are listed, dirs first."""
    (tmp_path / "dir_b").mkdir()
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "file_z.txt").touch()
    (tmp_path / "file_a.txt").touch()

    nav = DirectoryNavigator(root_dir=str(tmp_path))
    names = [node.name for node in nav.flat_list]
    
    # Dirs come first (sorted), then files (sorted)
    assert names == ["dir_a", "dir_b", "file_a.txt", "file_z.txt"]


def test_navigator_hides_dot_dirs(tmp_path):
    """Verify that hidden directories (starting with .) are excluded."""
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible").mkdir()

    nav = DirectoryNavigator(root_dir=str(tmp_path))
    names = [node.name for node in nav.flat_list]
    assert "visible" in names
    assert ".hidden" not in names


def test_navigator_render_returns_text():
    """Verify that the render method returns a Rich Text object."""
    from rich.text import Text
    nav = DirectoryNavigator()
    rendered = nav.render()
    assert isinstance(rendered, Text)
    assert "📂" in str(rendered)


def test_expand_directory(tmp_path):
    """Verify that expanding a directory adds its children to the flat list."""
    (tmp_path / "parent").mkdir()
    (tmp_path / "parent" / "child_dir").mkdir()
    (tmp_path / "parent" / "child_file.txt").touch()

    nav = DirectoryNavigator(root_dir=str(tmp_path))
    
    # Find the "parent" node
    parent_idx = next(i for i, n in enumerate(nav.flat_list) if n.name == "parent")
    parent_node = nav.flat_list[parent_idx]
    
    assert not parent_node.is_expanded
    
    # Expand
    nav._toggle_expand(parent_node)
    
    names = [n.name for n in nav.flat_list]
    assert "child_dir" in names
    assert "child_file.txt" in names
    
    # Verify parent is now expanded
    parent_node = nav.flat_list[parent_idx]
    assert parent_node.is_expanded


def test_collapse_directory(tmp_path):
    """Verify that collapsing a directory removes its children from the flat list."""
    (tmp_path / "parent").mkdir()
    (tmp_path / "parent" / "child").mkdir()

    nav = DirectoryNavigator(root_dir=str(tmp_path))
    parent_idx = next(i for i, n in enumerate(nav.flat_list) if n.name == "parent")
    parent_node = nav.flat_list[parent_idx]

    # Expand then collapse
    nav._toggle_expand(parent_node)
    assert any(n.name == "child" for n in nav.flat_list)

    parent_node = nav.flat_list[parent_idx]
    nav._toggle_expand(parent_node)
    assert not any(n.name == "child" for n in nav.flat_list)


def test_navigate_up_resets_root(tmp_path):
    """Verify that navigating up above the initial root resets it."""
    sub = tmp_path / "sub"
    sub.mkdir()

    nav = DirectoryNavigator(root_dir=str(sub))
    assert nav.initial_root == str(sub)

    nav._navigate_up()
    assert nav.root_dir == str(tmp_path)


def test_selection_path(tmp_path):
    """Verify that selecting an item returns the correct absolute path."""
    (tmp_path / "target_dir").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    
    idx = next(i for i, n in enumerate(nav.flat_list) if n.name == "target_dir")
    assert nav.flat_list[idx].path == str((tmp_path / "target_dir").resolve())


def test_navigator_expand_via_run(tmp_path, monkeypatch):
    """Verify that pressing Enter on a directory expands it in-place."""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "inner").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))

    # Select "subdir" (should be index 0)
    nav.selected_index = 0

    # Mock getch: enter (expand), then q (quit)
    keys = iter([b'\r', b'q'])
    monkeypatch.setattr("msvcrt.getch", lambda: next(keys))

    result = nav.run()
    # After expanding subdir, "inner" should be visible
    assert any(n.name == "inner" for n in nav.flat_list)


def test_ctrl_enter_exits_with_path(tmp_path, monkeypatch):
    """Verify CTRL+ENTER exits with the selected directory path."""
    (tmp_path / "target").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 0  # First item should be "target"

    monkeypatch.setattr("msvcrt.getch", lambda: b'\x0a')
    result = nav.run()
    assert result is not None
    assert os.path.isabs(result)
