from textual.app import App
from terminaltreeview.app import TreeViewApp
import pytest

@pytest.mark.asyncio
async def test_app_initialization():
    """Verify that the TreeViewApp can be initialized and started."""
    app = TreeViewApp()
    async with app.run_test() as pilot:
        assert app.title == "Terminal TreeView"
        assert app.sub_title == "Navigate and CD"
