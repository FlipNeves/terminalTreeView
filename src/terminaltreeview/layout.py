from rich.cells import cell_len
from rich.text import Text

MIN_WIDTH = 50
MIN_HEIGHT = 14

BOXES = {
    "rounded": ("╭", "╮", "╰", "╯", "─", "│", "├", "┤"),
    "ascii": ("+", "+", "+", "+", "-", "|", "+", "+"),
}


def compute_window(total: int, selected: int, budget: int) -> tuple[int, int] | None:
    budget = max(1, budget)
    if total <= budget:
        return None
    selected = min(max(selected, 0), total - 1)
    items = budget
    for _ in range(4):
        start = min(max(0, selected - items // 2), total - items)
        fits = budget - (1 if start > 0 else 0) - (1 if start + items < total else 0)
        if fits >= items:
            break
        items = max(1, fits)
    start = min(max(0, selected - items // 2), total - items)
    return start, start + items


def list_rows(height: int, fixed: int, footer: list) -> int:
    return max(1, height - 2 - fixed - len(footer) - (1 if footer else 0))


def clip_start(text: str, width: int) -> str:
    if cell_len(text) <= width:
        return text
    tail, used = [], 1
    for char in reversed(text):
        used += cell_len(char)
        if used > width:
            break
        tail.append(char)
    return "…" + "".join(reversed(tail))


def fit(text: Text, width: int) -> Text:
    line = text.copy()
    line.truncate(width, overflow="ellipsis", pad=True)
    return line


def boxed(box: tuple, styles: dict, title: str, body: list[Text], footer: list[Text],
          width: int, height: int) -> list[Text]:
    top_left, top_right, bottom_left, bottom_right, edge, side, tee_left, tee_right = box
    border = styles["border"]
    footer = footer[:max(0, height - 4)]
    rows = height - 2 - len(footer) - (1 if footer else 0)
    body = body[:rows] + [Text()] * (rows - len(body))

    def framed(text: Text) -> Text:
        line = Text()
        line.append(side + " ", style=border)
        line.append_text(fit(text, width - 4))
        line.append(" " + side, style=border)
        return line

    top = Text(top_left + edge, style=border)
    if title:
        top.append(f" {clip_start(title, width - 6)} ", style=styles["path"])
    top.append(edge * (width - 1 - top.cell_len) + top_right, style=border)
    lines = [top] + [framed(text) for text in body]
    if footer:
        lines.append(Text(tee_left + edge * (width - 2) + tee_right, style=border))
        lines += [framed(text) for text in footer]
    lines.append(Text(bottom_left + edge * (width - 2) + bottom_right, style=border))
    return lines


def centered(messages: list[Text], width: int, height: int) -> list[Text]:
    messages = messages[:height]
    top = (height - len(messages)) // 2
    lines = [Text() for _ in range(height)]
    for i, text in enumerate(messages):
        indent = max(0, (width - text.cell_len) // 2)
        lines[top + i] = Text(" " * indent) + text
    return [fit(line, width) for line in lines]
