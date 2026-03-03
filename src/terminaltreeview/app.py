import os
import sys
import readchar
from rich.console import Console
from rich.tree import Tree
from rich.live import Live

class DirectoryNavigator:
    def __init__(self, root_dir=None):
        self.root_dir = os.path.abspath(root_dir or os.getcwd())
        self.console = Console()
        self.selected_index = 0
        self.items = []
        self._refresh_items()

    def _refresh_items(self):
        try:
            # List directories only for now as per CD requirement
            self.items = [d for d in os.listdir(self.root_dir) if os.path.isdir(os.path.join(self.root_dir, d))]
            self.items.sort()
            # Add parent directory option
            self.items.insert(0, "..")
        except PermissionError:
            self.items = [".."]

    def render(self):
        tree = Tree(f"[bold blue]📂 {os.path.basename(self.root_dir) or self.root_dir}[/]")
        for i, item in enumerate(self.items):
            prefix = "> " if i == self.selected_index else "  "
            style = "bold cyan" if i == self.selected_index else "white"
            icon = "📁" if item != ".." else "⬆️"
            tree.add(f"{prefix}[{style}]{icon} {item}[/]")
        return tree

    def run(self):
        with Live(self.render(), console=self.console, refresh_per_second=10, transient=True) as live:
            while True:
                live.update(self.render())
                key = readchar.readkey()

                if key == readchar.key.UP:
                    self.selected_index = (self.selected_index - 1) % len(self.items)
                elif key == readchar.key.DOWN:
                    self.selected_index = (self.selected_index + 1) % len(self.items)
                elif key in (readchar.key.ENTER, readchar.key.RIGHT):
                    selected = self.items[self.selected_index]
                    self.root_dir = os.path.abspath(os.path.join(self.root_dir, selected))
                    self._refresh_items()
                    self.selected_index = 0
                elif key == readchar.key.LEFT:
                    self.root_dir = os.path.abspath(os.path.join(self.root_dir, ".."))
                    self._refresh_items()
                    self.selected_index = 0
                elif key in ('\x0a', '\x0d\x0a'): # Common CTRL+ENTER or alternative ENTER representations
                    # In many terminals, CTRL+ENTER sends LF (\n) while ENTER sends CR (\r)
                    selected = self.items[self.selected_index]
                    return os.path.abspath(os.path.join(self.root_dir, selected))
                elif key in ('q', readchar.key.CTRL_C):
                    return None

if __name__ == "__main__":
    nav = DirectoryNavigator()
    result = nav.run()
    if result:
        # Output result for shell wrapper
        print(result)
