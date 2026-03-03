import os
import pytest
from terminaltreeview.app import DirectoryNavigator

def test_navigator_initialization():
    """Verify that the DirectoryNavigator can be initialized."""
    nav = DirectoryNavigator()
    assert nav.root_dir == os.getcwd()
    assert ".." in nav.items

def test_navigator_render():
    """Verify that the render method returns a Tree object."""
    from rich.tree import Tree
    nav = DirectoryNavigator()
    tree = nav.render()
    assert isinstance(tree, Tree)
    assert "📂" in str(tree.label)
