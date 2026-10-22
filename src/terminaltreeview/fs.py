import os
import stat
from collections import deque
from typing import NamedTuple

_HIDDEN_ATTRIBUTES = stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM
_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003


class Entry(NamedTuple):
    name: str
    is_dir: bool
    is_link: bool = False


class Listing(NamedTuple):
    entries: list
    status: str | None = None
    error: str | None = None
    hidden: int = 0
    files: int = 0


def is_hidden(entry: os.DirEntry) -> bool:
    if entry.name.startswith("."):
        return True
    try:
        attributes = entry.stat(follow_symlinks=False).st_file_attributes
    except (OSError, AttributeError):
        return False
    return bool(attributes & _HIDDEN_ATTRIBUTES)


def _is_link(entry: os.DirEntry) -> bool:
    try:
        if entry.is_symlink():
            return True
        is_junction = getattr(entry, "is_junction", None)
        if is_junction is not None:
            return is_junction()
        return getattr(entry.stat(follow_symlinks=False), "st_reparse_tag", 0) == _IO_REPARSE_TAG_MOUNT_POINT
    except OSError:
        return False


def list_dir(path: str, show_hidden: bool = False, dirs_only: bool = False) -> Listing:
    dirs, files = [], []
    hidden = skipped_files = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if not show_hidden and is_hidden(entry):
                    hidden += 1
                    continue
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    is_dir = False
                if is_dir:
                    dirs.append(Entry(entry.name, True, _is_link(entry)))
                elif dirs_only:
                    skipped_files += 1
                else:
                    files.append(Entry(entry.name, False))
    except PermissionError:
        return Listing([], "denied")
    except OSError as error:
        return Listing([], "error", error.strerror or str(error))
    dirs.sort(key=lambda entry: entry.name.lower())
    files.sort(key=lambda entry: entry.name.lower())
    return Listing(dirs + files, None, None, hidden, skipped_files)


def walk(base: str, max_depth: int, show_hidden: bool = False, dirs_only: bool = False,
         skip=(), limit: int = 20000) -> tuple[list[tuple[str, Entry, int]], bool]:
    found = []
    skipped = {name.lower() for name in skip}
    queue = deque([(base, 0)])
    while queue:
        folder, depth = queue.popleft()
        for entry in list_dir(folder, show_hidden, dirs_only).entries:
            path = os.path.join(folder, entry.name)
            found.append((path, entry, depth))
            if len(found) >= limit:
                return found, True
            if entry.is_dir and not entry.is_link and depth + 1 < max_depth and entry.name.lower() not in skipped:
                queue.append((path, depth + 1))
    return found, False
