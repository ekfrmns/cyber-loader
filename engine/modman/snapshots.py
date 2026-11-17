"""Setup history: a small record of which mods were on (in order) and what each one looked like, so an older setup can be
put back and the old version of a mod can be named. A snapshot holds NO mod files, only names, versions and fingerprints."""
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .util import read_json, write_json

_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
MAX_AUTO = 200   # older automatic snapshots beyond this are moved to `old\` (never deleted)

# Library folders made from a Nexus download carry the mod number, version and upload date:
#   "<name> 4575 0.2.6 2026-10-26T08-38Z Q6xF6llYP"   (clear version)
#   "<name>-4575-0-2-6-1698765432"                     (older style: the version has its dots turned into dashes)
_NEW = re.compile(r"\s+(\d{3,6})\s+([\dv][\w.\-]*)\s+(\d{4}-\d\d-\d\d)T[\w-]+Z\s+\w+(?: \((?:\d+|restored(?: \d+)?)\))?$")
_OLD = re.compile(r"-(\d{3,6})-([\w-]*)-(\d{9,})(?: \((?:\d+|restored(?: \d+)?)\))?$")


def parse_origin(folder: str) -> dict:
    """What a library folder name says about where the mod came from: {nexusId, version, date}; {} if nothing.
    The version is shown as written (the older style cannot be turned back into dots reliably)."""
    m = _NEW.search(folder)
    if m:
        return {"nexusId": int(m.group(1)), "version": m.group(2).lstrip("v") or None, "date": m.group(3), "style": "clear"}
    m = _OLD.search(folder)
    if m:
        date = None
        try:
            date = datetime.fromtimestamp(int(m.group(3)), timezone.utc).strftime("%Y-%m-%d")
        except (OverflowError, OSError, ValueError):
            pass
        return {"nexusId": int(m.group(1)), "version": m.group(2) or None, "date": date, "style": "squashed"}
    return {}


def pretty_version(origin: dict):
    """A version for people to read: the older Nexus style writes "2-0-1" for 2.0.1, so its dashes become dots."""
    v = origin.get("version")
    if v and origin.get("style") == "squashed":
        v = v.replace("-", ".")
    return v


def describe(mod) -> dict:
    """One library mod as a snapshot remembers it."""
    origin = {k: v for k, v in parse_origin(mod.id).items() if k != "style"}
    return {"id": mod.id, "name": mod.name, "files": len(mod.files), "size": mod.size, **origin}


class Snapshots:
    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def _path(self, sid: str) -> Path:
        if not _ID.match(sid or ""):
            raise KeyError("not a snapshot")
        return self.folder / f"{sid}.json"

    def save(self, mods: list, profile, auto: bool, name: str = None) -> str:
        """`mods`: ordered list of described mods (see describe). Returns the new snapshot id."""
        sid = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
        write_json(self._path(sid), {"id": sid, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "profile": profile, "auto": auto,
                                     "pinned": False, "name": (name or "").strip() or None, "ts": time.time_ns(), "mods": mods})
        self.prune()
        return sid

    def load(self, sid: str) -> dict:
        d = read_json(self._path(sid))
        if d is None:
            raise KeyError("that snapshot no longer exists")
        return d

    def all(self) -> list:
        """Every snapshot, newest first."""
        if not self.folder.exists():
            return []
        out = []
        for p in self.folder.glob("*.json"):
            if _ID.match(p.stem):
                d = read_json(p)
                if isinstance(d, dict) and isinstance(d.get("mods"), list):
                    out.append(d)
        return sorted(out, key=lambda d: (d.get("ts", 0), d["id"]), reverse=True)   # ts orders snapshots made in the same second

    def latest(self):
        found = self.all()
        return found[0] if found else None

    def same_as_latest(self, mods: list, profile) -> bool:
        """True if the newest snapshot already shows exactly this setup (same mods, order, versions, fingerprints)."""
        last = self.latest()
        return bool(last) and last.get("profile") == profile and last["mods"] == mods

    def pin(self, sid: str, pinned: bool, name=None) -> dict:
        d = self.load(sid)
        d["pinned"] = bool(pinned)
        if name is not None:
            d["name"] = name.strip() or None
        write_json(self._path(sid), d)
        return d

    def prune(self) -> None:
        """Keep the newest MAX_AUTO automatic snapshots. Older ones move to old\\ (nothing is erased); pinned and named ones stay."""
        auto = [d for d in self.all() if d.get("auto") and not d.get("pinned") and not d.get("name")]
        for d in auto[MAX_AUTO:]:
            old = self.folder / "old"
            old.mkdir(exist_ok=True)
            shutil.move(str(self._path(d["id"])), str(old / f"{d['id']}.json"))
