import os
import sys
import msvcrt
from rich.console import Console
from rich.tree import Tree

class DirectoryNavigator:
    def __init__(self, root_dir=None):
        self.root_dir = os.path.abspath(root_dir or os.getcwd())
        # force_terminal=True is critical when stdout is being captured by a shell wrapper
        self.console = Console(stderr=True, force_terminal=True)
        self.selected_index = 0
        self.items = []
        self._refresh_items()
        self.last_line_count = 0

    def _refresh_items(self):
        try:
            self.items = [d for d in os.listdir(self.root_dir) if os.path.isdir(os.path.join(self.root_dir, d))]
            self.items.sort()
            self.items.insert(0, "..")
        except PermissionError:
            self.items = [".."]
        
        if self.selected_index >= len(self.items):
            self.selected_index = 0

    def render(self):
        tree = Tree(f"[bold blue]📂 {os.path.basename(self.root_dir) or self.root_dir}[/]")
        for i, item in enumerate(self.items):
            prefix = "> " if i == self.selected_index else "  "
            style = "bold cyan" if i == self.selected_index else "white"
            icon = "📁" if item != ".." else "⬆️"
            tree.add(f"{prefix}[{style}]{icon} {item}[/]")
        return tree

    def clear_previous_render(self):
        """Move cursor up and clear lines from the previous render."""
        if self.last_line_count > 0:
            # ANSI escape: ESC [ <N> A (move up N lines), ESC [ J (clear from cursor to end of screen)
            # We use \033[F to move to the beginning of the previous line and \033[K to clear the line
            for _ in range(self.last_line_count):
                sys.stderr.write("\033[F\033[K")
            sys.stderr.flush()

    def get_key(self):
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            ch = msvcrt.getch()
            return {b'H': 'up', b'P': 'down', b'M': 'right', b'K': 'left'}.get(ch)
        if ch == b'\r': return 'enter'
        if ch == b'\x0a': return 'ctrl_enter'
        if ch == b'\x03': return 'ctrl_c'
        if ch == b'q': return 'quit'
        return None

    def run(self):
        while True:
            self.clear_previous_render()
            
            # Use capture to determine the number of lines rendered
            with self.console.capture() as capture:
                self.console.print(self.render())
            
            output = capture.get()
            self.console.print(self.render()) # Actually print to stderr
            self.last_line_count = output.count('\n') 
            
            key = self.get_key()

            if key == 'up':
                self.selected_index = (self.selected_index - 1) % len(self.items)
            elif key == 'down':
                self.selected_index = (self.selected_index + 1) % len(self.items)
            elif key in ('enter', 'right'):
                selected = self.items[self.selected_index]
                new_path = os.path.abspath(os.path.join(self.root_dir, selected))
                if os.path.isdir(new_path):
                    self.root_dir = new_path
                    self._refresh_items()
                    self.selected_index = 0
            elif key == 'left':
                self.root_dir = os.path.abspath(os.path.join(self.root_dir, ".."))
                self._refresh_items()
                self.selected_index = 0
            elif key == 'ctrl_enter':
                # Clear before exit so it doesn't leave junk in the terminal
                self.clear_previous_render()
                selected = self.items[self.selected_index]
                if selected == "..":
                    return self.root_dir
                return os.path.abspath(os.path.join(self.root_dir, selected))
            elif key in ('quit', 'ctrl_c'):
                self.clear_previous_render()
                return None

if __name__ == "__main__":
    nav = DirectoryNavigator()
    result = nav.run()
    if result:
        sys.stdout.write(result + '\n')
        sys.stdout.flush()
