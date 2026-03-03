import os
import pathlib

def test_project_structure():
    """Verify that the basic project structure exists."""
    root = pathlib.Path(__file__).parent.parent
    assert (root / "pyproject.toml").exists()
    assert (root / "src").is_dir()
    assert (root / "src" / "terminaltreeview").is_dir()
    assert (root / "tests").is_dir()

def test_dependencies_configured():
    """Verify that readchar and rich are in pyproject.toml."""
    root = pathlib.Path(__file__).parent.parent
    pyproject = root / "pyproject.toml"
    assert pyproject.exists()
    content = pyproject.read_text()
    assert "readchar" in content
    assert "rich" in content
    assert "pytest" in content
