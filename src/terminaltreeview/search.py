import unicodedata
from functools import lru_cache

_SEPARATORS = frozenset(" _-.()[]{}+,;=@#&!~'")


@lru_cache(maxsize=4096)
def _fold_char(ch: str) -> str:
    base = unicodedata.normalize("NFD", ch)[0]
    lowered = base.lower()
    return lowered if len(lowered) == 1 else base


@lru_cache(maxsize=65536)
def _fold(text: str) -> str:
    if text.isascii():
        return text.lower()
    return "".join(_fold_char(ch) for ch in text)


def _boundary(name: str, index: int) -> bool:
    if index == 0:
        return True
    previous, current = name[index - 1], name[index]
    return previous in _SEPARATORS or (previous.islower() and current.isupper())


def _contiguous_score(name: str, start: int, size: int) -> int:
    score = 1000
    if start == 0:
        score += 400
    elif _boundary(name, start):
        score += 200
    if size == len(name):
        score += 600
    return score - (len(name) - size)


def _fuzzy_score(name: str, positions: list[int]) -> int:
    score = 200 - (positions[-1] - positions[0])
    for k, position in enumerate(positions):
        if _boundary(name, position):
            score += 20
        if k and position == positions[k - 1] + 1:
            score += 15
    if positions[0] == 0:
        score += 30
    return score - len(name) // 4


def _greedy(query: str, folded: str, start: int) -> list[int] | None:
    positions = [start]
    index = start + 1
    for ch in query[1:]:
        index = folded.find(ch, index)
        if index < 0:
            return None
        positions.append(index)
        index += 1
    return positions


def match(query: str, name: str, mode: str = "fuzzy") -> tuple[int, list[int]] | None:
    folded_query = _fold(query)
    folded = _fold(name)
    if not folded_query:
        return 0, []
    if mode == "prefix":
        if not folded.startswith(folded_query):
            return None
        return _contiguous_score(name, 0, len(folded_query)), list(range(len(folded_query)))

    start = folded.find(folded_query)
    if start >= 0:
        best = start
        probe = start
        while probe >= 0 and not _boundary(name, probe):
            probe = folded.find(folded_query, probe + 1)
        if probe >= 0:
            best = probe
        return _contiguous_score(name, best, len(folded_query)), list(range(best, best + len(folded_query)))
    if mode == "contains":
        return None

    best_positions, best_score = None, 0
    start = folded.find(folded_query[0])
    attempts = 0
    while start >= 0 and attempts < 8:
        positions = _greedy(folded_query, folded, start)
        if positions is None:
            break
        score = _fuzzy_score(name, positions)
        if best_positions is None or score > best_score:
            best_positions, best_score = positions, score
        start = folded.find(folded_query[0], start + 1)
        attempts += 1
    if best_positions is None:
        return None
    return best_score, best_positions
