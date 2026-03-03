from textual.app import App, ComposeResult
from textual.widgets import Header, Footer

class TreeViewApp(App):
    """A Textual app to navigate directories."""
    
    TITLE = "Terminal TreeView"
    SUB_TITLE = "Navigate and CD"
    
    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

if __name__ == "__main__":
    app = TreeViewApp()
    app.run()
