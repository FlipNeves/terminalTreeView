import os
import pytest
from terminaltreeview.app import DirectoryNavigator

def test_navigator_initialization():
    """Verify that the DirectoryNavigator can be initialized."""
    nav = DirectoryNavigator()
    assert nav.root_dir == os.getcwd()
    assert ".." in nav.items

def test_navigator_lists_directories(tmp_path):
    """Verify that only directories are listed."""
    # Create a dummy structure
    (tmp_path / "dir1").mkdir()
    (tmp_path / "dir2").mkdir()
    (tmp_path / "file1.txt").touch()
    
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    # items should be ['..', 'dir1', 'dir2']
    assert "dir1" in nav.items
    assert "dir2" in nav.items
    assert "file1.txt" not in nav.items
    assert nav.items[0] == ".."

def test_navigator_render():
    """Verify that the render method returns a Tree object."""
    from rich.tree import Tree
    nav = DirectoryNavigator()
    tree = nav.render()
    assert isinstance(tree, Tree)
    assert "📂" in str(tree.label)
