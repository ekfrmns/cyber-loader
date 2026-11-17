"""Deploy engine: turn "these mods are on" into files in the game folder, and undo it again.

Safety rules (all enforced here, covered by tests):
  * Only files this engine recorded in state/deployed.json are ever removed.
  * A recorded file that was changed since deployment is left in place and reported, never deleted.
  * A file that already exists and is not ours blocks the apply (nothing is overwritten).
  * Directories are only removed if this engine created them and they are now empty.
"""
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .util import key, process_running, read_json, sha256, write_json
from .config import GAME_EXE


# Files a mod regenerates itself every launch (e.g. Input Loader merges bindings into these). They always count
# as "modified", so on removal they are moved aside (kept, never deleted) instead of being left in the game folder.
GENERATED = {key(r"r6\cache\inputContexts.xml"), key(r"r6\cache\inputUserMappings.xml")}


@dataclass
class Entry:
    rel: str
    mod: str
    src: Path


class State:
    """What this engine has placed in the game folder."""

    def __init__(self, path: Path):
        self.path = Path(path)
        d = read_json(self.path, {}) or {}
        self.files: dict = d.get("files", {})      # key -> {rel, mod, mode, size, mtime_ns, ino}
        self.dirs: list = d.get("dirs", [])        # directories (game-relative) this engine created
        self.left: set = set(d.get("left", []))    # keys of modified files left behind on removal
        self.profile = d.get("profile")
        self.saved_at = d.get("saved_at")

    def save(self) -> None:
        write_json(self.path, {
            "version": 1, "profile": self.profile, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "files": self.files, "dirs": self.dirs, "left": sorted(self.left),
        })

    def deployed_mods(self) -> set:
        return {r["mod"] for r in self.files.values()}


@dataclass
class Plan:
    adds: list = field(default_factory=list)       # Entry
    removes: list = field(default_factory=list)    # (key, record)
    adopts: list = field(default_factory=list)     # (Entry, modified:bool)
    keeps: int = 0
    blocked: list = field(default_factory=list)    # {rel, reason}
    left: list = field(default_factory=list)       # {rel, reason}: removal skipped, file modified
    conflicts: list = field(default_factory=list)  # {path, winner, losers}
    warnings: list = field(default_factory=list)

    def summary(self) -> dict:
        return {"add": len(self.adds), "remove": len(self.removes), "adopt": len(self.adopts),
                "keep": self.keeps, "blocked": len(self.blocked), "left": len(self.left),
                "conflicts": len(self.conflicts)}


# ---------------------------------------------------------------- desired state
def build_desired(library, enabled_ids):
    """Map key -> Entry for the given mods in order (later wins) plus the list of conflicts."""
    files: dict = {}
    seen: dict = {}
    for mid in enabled_ids:
        mod = library.mods.get(mid)
        if mod is None:
            continue
        for k, rel in mod.files.items():
            if k in files and files[k].mod != mid:
                seen.setdefault(k, [files[k].mod]).append(mid)
            files[k] = Entry(rel, mid, mod.src(rel))
    conflicts = [{"path": files[k].rel, "winner": mods[-1], "losers": mods[:-1]} for k, mods in seen.items()]
    return files, conflicts


def conflict_counts(conflicts) -> dict:
    n: dict = {}
    for c in conflicts:
        for m in [c["winner"], *c["losers"]]:
            n[m] = n.get(m, 0) + 1
    return n


# ---------------------------------------------------------------- checks
def _stat(path):
    try:
        return os.stat(path)
    except FileNotFoundError:
        return None


def intact(dst: Path, rec: dict):
    """None = missing, True = still exactly what we deployed, False = changed by someone else."""
    st = _stat(dst)
    if st is None:
        return None
    if rec["mode"] == "link":
        return st.st_ino == rec["ino"] and st.st_size == rec["size"]
    return st.st_size == rec["size"] and st.st_mtime_ns == rec["mtime_ns"]


def _identical(a: Path, b: Path) -> bool:
    sa, sb = _stat(a), _stat(b)
    if sa is None or sb is None or sa.st_size != sb.st_size:
        return False
    if sa.st_ino == sb.st_ino and sa.st_ino != 0:
        return True
    return sha256(a) == sha256(b)


_proc_cache: dict = {}


def _running(image: str, fresh: bool, ttl: float = 2.0) -> bool:
    """process_running() launches `tasklist` (about 150 ms), so UI polling uses a short-lived cache.
    Anything that decides whether it is safe to change files must pass fresh=True."""
    now = time.time()
    hit = _proc_cache.get(image)
    if hit and not fresh and now - hit[0] < ttl:
        return hit[1]
    val = process_running(image)
    _proc_cache[image] = (now, val)
    return val


def game_running(fresh: bool = False) -> bool:
    return _running(GAME_EXE, fresh)


def preflight(cfg, fresh: bool = True) -> dict:
    return {"game_running": _running(GAME_EXE, fresh), "vortex_running": _running("Vortex.exe", fresh)}


# ---------------------------------------------------------------- planning
def make_plan(cfg, library, enabled_ids, state: State) -> Plan:
    plan = Plan()
    desired, plan.conflicts = build_desired(library, enabled_ids)
    game = cfg.game
    for k, e in desired.items():
        dst = game / e.rel
        rec = state.files.get(k)
        if rec and rec["mod"] == e.mod:
            ok = intact(dst, rec)
            if ok is None:
                plan.adds.append(e)            # went missing: restore it
            else:
                plan.keeps += 1                # present (even if the user edited it: theirs stays)
            continue
        if rec:                                # a different mod owns it now: swap
            ok = intact(dst, rec)
            if ok is False:
                plan.blocked.append({"rel": e.rel, "reason": f"modified after {rec['mod']} placed it; cannot replace"})
                continue
            plan.removes.append((k, rec))
            plan.adds.append(e)
            continue
        if _stat(dst) is not None:
            if _identical(dst, e.src):
                plan.adopts.append((e, False))
            elif k in state.left:
                plan.adopts.append((e, True))  # our old file, modified by the user: keep their version
            else:
                plan.blocked.append({"rel": e.rel, "reason": "a file that is not from this manager already exists here"})
            continue
        plan.adds.append(e)
    for k, rec in state.files.items():
        if k in desired:
            continue
        ok = intact(game / rec["rel"], rec)
        if ok is False and k not in GENERATED:
            plan.left.append({"rel": rec["rel"], "reason": f"modified since {rec['mod']} placed it; will be left in place"})
        plan.removes.append((k, rec))
    return plan


# ---------------------------------------------------------------- applying
def _record(dst: Path, entry: Entry, mode: str) -> dict:
    st = os.stat(dst)
    return {"rel": entry.rel, "mod": entry.mod, "mode": mode, "size": st.st_size,
            "mtime_ns": st.st_mtime_ns, "ino": st.st_ino}


def _make_dirs(game: Path, rel_parent: str, state: State) -> None:
    parts = [p for p in rel_parent.split("\\") if p]
    cur = game
    acc = ""
    for p in parts:
        cur = cur / p
        acc = acc + "\\" + p if acc else p
        if not cur.exists():
            cur.mkdir()
            if acc not in state.dirs:
                state.dirs.append(acc)


def apply_plan(cfg, plan: Plan, state: State, progress=None, log=None) -> dict:
    """Execute a plan. Returns {"errors": [...], "done": n}. Writes state as it goes."""
    log = log or (lambda m: None)
    game = cfg.game
    total = max(1, len(plan.removes) + len(plan.adds) + len(plan.adopts))
    done = 0
    errors = []

    def tick(text):
        nonlocal done
        done += 1
        if progress:
            progress(min(99, int(done * 100 / total)), text)
        if done % 100 == 0:
            state.save()

    for k, rec in plan.removes:
        dst = game / rec["rel"]
        try:
            ok = intact(dst, rec)
            if ok is True:
                os.remove(dst)
                log(f"removed {rec['rel']}  ({rec['mod']})")
            elif ok is False and k in GENERATED:
                aside = cfg.state_dir / "moved-aside" / time.strftime("%Y-%m-%d_%H-%M-%S") / rec["rel"]
                aside.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(aside))
                log(f"moved aside (regenerated by the mod) {rec['rel']}  ->  {aside}")
            elif ok is False:
                state.left.add(k)
                log(f"LEFT (modified) {rec['rel']}  ({rec['mod']})")
            state.files.pop(k, None)
        except OSError as ex:
            errors.append(f"remove {rec['rel']}: {ex}")
            log(f"ERROR remove {rec['rel']}: {ex}")
        tick(f"Removing {Path(rec['rel']).name}")

    for d in sorted(state.dirs, key=len, reverse=True):  # prune empty directories we created
        p = game / d
        try:
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
                state.dirs.remove(d)
            elif not p.exists():
                state.dirs.remove(d)
        except OSError:
            pass

    for e, modified in plan.adopts:
        k = key(e.rel)
        dst = game / e.rel
        try:
            same = _stat(dst).st_ino == _stat(e.src).st_ino
            state.files[k] = _record(dst, e, "link" if same else "copy")
            state.left.discard(k)
            log(f"adopted {e.rel}{' (user-modified, kept)' if modified else ''}  ({e.mod})")
        except OSError as ex:
            errors.append(f"adopt {e.rel}: {ex}")
        tick(f"Checking {Path(e.rel).name}")

    for e in plan.adds:
        k = key(e.rel)
        dst = game / e.rel
        try:
            _make_dirs(game, str(Path(e.rel).parent).replace("/", "\\") if str(Path(e.rel).parent) != "." else "", state)
            size = e.src.stat().st_size
            mode = "copy"
            if size >= cfg.link_min_bytes:
                try:
                    os.link(e.src, dst)
                    mode = "link"
                except OSError:
                    mode = "copy"
            if mode == "copy":
                shutil.copy2(e.src, dst)
            state.files[k] = _record(dst, e, mode)
            state.left.discard(k)
            log(f"added {e.rel}  ({e.mod}, {mode})")
        except OSError as ex:
            errors.append(f"add {e.rel}: {ex}")
            log(f"ERROR add {e.rel}: {ex}")
        tick(f"Placing {Path(e.rel).name}")

    state.save()
    if progress:
        progress(100, "Done" if not errors else f"Finished with {len(errors)} problem(s)")
    return {"errors": errors, "done": done}
