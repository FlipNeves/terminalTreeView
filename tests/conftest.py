import pytest

from terminaltreeview import app as app_module
from terminaltreeview.app import DirectoryNavigator
from terminaltreeview.config import Config


@pytest.fixture(autouse=True)
def utf8_console(monkeypatch):
    monkeypatch.setattr(app_module, "_console_code_page", lambda: 65001)


@pytest.fixture
def make_nav():
    def make(root, keys=None, config=None, **options):
        if config is None:
            config = Config()
            config.layout.language = "en"
        for option_id, value in options.items():
            config.set(option_id.replace("__", "."), value)
        source = iter(keys).__next__ if keys is not None else None
        nav = DirectoryNavigator(root_dir=str(root), config=config, key_source=source)
        nav._get_window_size = lambda: (200, 40)
        return nav
    return make
