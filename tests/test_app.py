import os
import pytest
import readchar
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
    
    # items = ['..', 'target_dir']
    nav.selected_index = 1
    selected_item = nav.items[nav.selected_index]
    result_path = os.path.abspath(os.path.join(nav.root_dir, selected_item))
    assert result_path == str((tmp_path / "target_dir").resolve())

def test_navigator_navigation(tmp_path, monkeypatch):
    """Verify ENTER moves into a directory."""
    (tmp_path / "subdir").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    
    # Force select 'subdir'
    nav.selected_index = 1
    
    # Mock readchar to return ENTER, then 'q' to exit loop
    # Wait, nav.run() has a loop that only exits on specific keys.
    # We need to mock a sequence of keys.
    keys = iter([readchar.key.ENTER, 'q'])
    monkeypatch.setattr("readchar.readkey", lambda: next(keys))
    
    # Since Live rendering is complex in tests, we might want to mock it 
    # but the logic itself is what we want to test.
    result = nav.run()
    
    assert result is None # Exited with 'q'
    assert nav.root_dir == os.path.abspath(os.path.join(tmp_path, "subdir"))

def test_navigator_select_and_exit(tmp_path, monkeypatch):
    """Verify CTRL+ENTER exits with path."""
    (tmp_path / "subdir").mkdir()
    nav = DirectoryNavigator(root_dir=str(tmp_path))
    
    # Highlight 'subdir'
    nav.selected_index = 1
    
    # Mock readchar to return CTRL+ENTER (\x0a)
    monkeypatch.setattr("readchar.readkey", lambda: '\x0a')
    
    result = nav.run()
    assert result == os.path.abspath(os.path.join(tmp_path, "subdir"))
