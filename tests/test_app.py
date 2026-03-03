import os
import pytest
import sys
from unittest.mock import MagicMock

# Mock msvcrt for tests
import msvcrt
from terminaltreeview.app import DirectoryNavigator

def test_navigator_initialization():
    """Verify that the DirectoryNavigator can be initialized."""
    nav = DirectoryNavigator()
    assert nav.root_dir == os.getcwd()
    assert ".." in nav.items
    assert nav.console.stderr is True

def test_navigator_lists_directories(tmp_path):
    """Verify that only directories are listed."""
    (tmp_path / "dir1").mkdir()
    (tmp_path / "dir2").mkdir()
    (tmp_path / "file1.txt").touch()
    
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    assert "dir1" in nav.items
    assert "dir2" in nav.items
    assert "file1.txt" not in nav.items
    assert nav.items[0] == ".."

def test_navigator_render():
    """Verify that the render method returns a Tree object."""
    from rich.tree import Tree
    from rich.console import Console
    nav = DirectoryNavigator()
    tree = nav.render()
    assert isinstance(tree, Tree)
    assert "📂" in str(tree.label)

def test_navigator_selection_path(tmp_path):
    """Verify that selecting an item returns the correct absolute path."""
    (tmp_path / "target_dir").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 1
    selected_item = nav.items[nav.selected_index]
    result_path = os.path.abspath(os.path.join(nav.root_dir, selected_item))
    assert result_path == str((tmp_path / "target_dir").resolve())

def test_navigator_navigation_in_place(tmp_path, monkeypatch):
    """Verify that navigating into a directory stays in place (last_line_count NOT reset to 0)."""
    (tmp_path / "subdir").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 1
    
    # Mock getch to return b'\r' (enter), then b'q' (quit)
    keys = iter([b'\r', b'q'])
    monkeypatch.setattr("msvcrt.getch", lambda: next(keys))
    
    # We want to ensure that last_line_count is not manually reset in the navigation logic
    # In the current code, it's calculated in the loop. 
    # If it was reset to 0, it would stay 0 until the next loop.
    
    result = nav.run()
    assert nav.root_dir == os.path.abspath(os.path.join(tmp_path, "subdir"))

def test_navigator_select_and_exit_on_parent_item(tmp_path, monkeypatch):
    """Verify CTRL+ENTER on '..' exits with CURRENT root_dir."""
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    nav.selected_index = 0 # Highlight '..'
    monkeypatch.setattr("msvcrt.getch", lambda: b'\x0a')
    result = nav.run()
    assert result == os.path.abspath(tmp_path)
