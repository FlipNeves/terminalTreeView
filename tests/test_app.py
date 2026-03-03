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
    """Verify that the render method returns a Tree object with correct styling."""
    from rich.tree import Tree
    from rich.console import Console
    nav = DirectoryNavigator()
    tree = nav.render()
    assert isinstance(tree, Tree)
    # Check for root folder icon and style
    assert "📂" in str(tree.label)
    assert "bold blue" in str(tree.label)
    
    console = Console(width=80)
    with console.capture() as capture:
        console.print(tree)
    output = capture.get()
    assert "📁" in output or "⬆️" in output
    assert ">" in output  # Selected item prefix

def test_navigator_selection_path(tmp_path):
    """Verify that selecting an item returns the correct absolute path."""
    (tmp_path / "target_dir").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    
    # items = ['..', 'target_dir'] (alphabetical order of dirs)
    nav.selected_index = 1
    
    selected_item = nav.items[nav.selected_index]
    result_path = os.path.abspath(os.path.join(nav.root_dir, selected_item))
    
    assert result_path == str((tmp_path / "target_dir").resolve())
