"""Profiles: a named, ordered list of library mod ids. Later entries win file conflicts."""
import re
from pathlib import Path

from .util import read_json, write_json


def _safe(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", name).strip()
    if not s:
        raise ValueError("profile name is empty")
    return s


class Profiles:
    def __init__(self, folder: Path, state_file: Path):
        self.folder = Path(folder)
        self.state_file = Path(state_file)  # remembers the selected profile

    def _path(self, name: str) -> Path:
        return self.folder / (_safe(name) + ".json")

    def names(self) -> list:
        if not self.folder.exists():
            return []
        order = (read_json(self.state_file, {}) or {}).get("order", [])
        found = [read_json(p, {}).get("name", p.stem) for p in self.folder.glob("*.json")]
        return sorted(found, key=lambda n: (order.index(n) if n in order else 999, n.lower()))

    def load(self, name: str) -> list:
        d = read_json(self._path(name))
        if d is None:
            raise KeyError(f"no profile called {name!r}")
        return list(d.get("mods", []))

    def save(self, name: str, mods: list) -> None:
        write_json(self._path(name), {"name": name, "mods": list(mods)})

    def delete(self, name: str) -> None:
        p = self._path(name)
        if not p.exists():
            raise KeyError(f"no profile called {name!r}")
        p.unlink()

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def rename(self, old: str, new: str) -> str:
        """Rename a profile (file, remembered order and selection). Returns the cleaned new name."""
        new = new.strip()
        if not new:
            raise ValueError("the new name is empty")
        mods = self.load(old)
        if new.lower() != old.lower() and any(n.lower() == new.lower() for n in self.names()):
            raise FileExistsError(f"a profile called {new!r} already exists")
        old_path = self._path(old)
        self.save(new, mods)
        if self._path(new) != old_path:       # (a pure case change maps to the same file on Windows)
            old_path.unlink()
        s = read_json(self.state_file, {}) or {}
        if s.get("current") == old:
            s["current"] = new
        s["order"] = [new if n == old else n for n in s.get("order", [])]
        write_json(self.state_file, s)
        return new

    # selected profile
    def current(self):
        return (read_json(self.state_file, {}) or {}).get("current")

    def set_current(self, name: str) -> None:
        s = read_json(self.state_file, {}) or {}
        s["current"] = name
        write_json(self.state_file, s)

    def set_order(self, names: list) -> None:
        s = read_json(self.state_file, {}) or {}
        s["order"] = list(names)
        write_json(self.state_file, s)
