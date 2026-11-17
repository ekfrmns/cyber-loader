"""Application layer shared by the CLI and the local API server."""
import os
import re
import threading
import time
from pathlib import Path

from . import __version__, msgpack_min
from .config import Config
from .deploy import (Entry, Plan, State, _identical, _stat, apply_plan, build_desired, conflict_counts, game_running,
                     intact, make_plan, preflight)
from .library import Library, clean_name, normalize_root
from .profiles import Profiles
from .util import key, read_json, write_json


class ApiError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class App:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        cfg.ensure()
        self.lock = threading.RLock()
        self.library = Library(cfg.library)
        self.library.scan()
        self.profiles = Profiles(cfg.profiles_dir, cfg.state_dir / "session.json")
        self.state = State(cfg.state_dir / "deployed.json")
        if not self.profiles.names():       # first run: start with one empty profile (= the plain game)
            self.profiles.save("Empty", [])
            self.profiles.set_current("Empty")
        self.current = self.profiles.current()
        self.working: list = []
        if self.current and self.profiles.exists(self.current):
            self.working = [m for m in self.profiles.load(self.current) if m in self.library.mods]
        self.job = {"state": "idle", "percent": 0, "text": ""}
        self.uploads: dict = {}
        self.last_request = time.time()
        self._sweep_tmp()

    def _sweep_tmp(self) -> None:
        """Remove unfinished upload/import work folders older than a day."""
        import shutil
        try:
            for d in self.cfg.tmp_dir.iterdir():
                if d.is_dir() and d.name.startswith(("upload-", "import-")) and time.time() - d.stat().st_mtime > 86400:
                    shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass

    # ------------------------------------------------------------ views
    def state_view(self) -> dict:
        with self.lock:
            enabled = set(self.working)
            deployed = self.state.deployed_mods()
            _, conflicts = build_desired(self.library, self.working)
            cc = conflict_counts(conflicts)
            mods, on, off = [], 0, 0
            providers = self.library.providers()
            for m in self.library.mods.values():
                v = self._mod_view(m, enabled, deployed, cc, self.library.auto_requires(m, providers))
                if v["pending"] == "on":
                    on += 1
                elif v["pending"] == "off":
                    off += 1
                mods.append(v)
            return {"game": {"running": game_running(), "found": self.cfg.game_found}, "profile": self.current,
                    "profiles": self.profiles.names(), "deployedCount": len(self.state.files),
                    "pendingCount": {"on": on, "off": off}, "profileDirty": self._profile_dirty(),
                    "version": __version__, "mods": mods}

    @staticmethod
    def _mod_view(m, enabled: set, deployed: set, cc: dict, auto=None) -> dict:
        pending = None
        if m.id in enabled and m.id not in deployed:
            pending = "on"
        elif m.id not in enabled and m.id in deployed:
            pending = "off"
        return {"id": m.id, "name": m.name, "group": m.group, "files": len(m.files), "enabled": m.id in enabled,
                "pending": pending, "framework": m.framework, "requires": m.requires, "autoRequires": auto or [], "conflicts": cc.get(m.id, 0)}

    def _profile_dirty(self) -> bool:
        """True if the staged mod set differs from the saved profile."""
        if not self.current or not self.profiles.exists(self.current):
            return False
        saved = {m for m in self.profiles.load(self.current) if m in self.library.mods}
        return saved != set(self.working)

    def discard(self) -> dict:
        """Throw away staged changes: the staged set becomes exactly what is deployed now."""
        with self.lock:
            deployed = self.state.deployed_mods()
            keep = [m for m in self.working if m in deployed]
            keep += sorted((m for m in deployed if m in self.library.mods and m not in keep), key=str.lower)
            self.working = keep
            return self.state_view()

    def _warning_items(self) -> list:
        """[(mod id, ids of the mods that would fix it, text)] for every unmet need of an enabled mod."""
        items = []
        enabled = set(self.working)
        providers = self.library.providers()
        for mid in self.working:
            m = self.library.mods[mid]
            for r in m.requires:
                if r not in enabled:
                    rn = self.library.mods[r].name if r in self.library.mods else r
                    items.append((mid, [r], f"{m.name} needs {rn}, which is off"))
            for need in self.library.auto_requires(m, providers):   # guessed from the mod's files
                if any(i in enabled for i in need["ids"]):
                    continue
                why = "which is off" if need["ids"] else "which is not in your library"
                items.append((mid, need["ids"], f"{m.name} needs {need['name']}, {why}"))
        return items

    def _warnings(self) -> list:
        return [text for _, _, text in self._warning_items()]

    # ------------------------------------------------------------ toggling and profiles
    def toggle(self, mod_id: str, enabled: bool) -> dict:
        with self.lock:
            if mod_id not in self.library.mods:
                raise ApiError(404, f"unknown mod: {mod_id}")
            if enabled and mod_id not in self.working:
                self.working.append(mod_id)
            elif not enabled and mod_id in self.working:
                self.working.remove(mod_id)
            # warnings about this mod's own needs, and (when turned off) about enabled mods that need this one
            warns = [text for mid, fixers, text in self._warning_items() if mid == mod_id or (not enabled and mod_id in fixers)]
            _, conflicts = build_desired(self.library, self.working)
            view = self._mod_view(self.library.mods[mod_id], set(self.working), self.state.deployed_mods(), conflict_counts(conflicts),
                                  self.library.auto_requires(self.library.mods[mod_id]))
            return {"ok": True, "mod": view, "warnings": sorted(set(warns))}

    def select_profile(self, name: str) -> dict:
        with self.lock:
            if not self.profiles.exists(name):
                raise ApiError(404, f"no profile called {name!r}")
            self.working = [m for m in self.profiles.load(name) if m in self.library.mods]
            self.current = name
            self.profiles.set_current(name)
            return self.state_view()

    def save_profile(self, name: str) -> None:
        with self.lock:
            self.profiles.save(name, self.working)
            self.current = name
            self.profiles.set_current(name)

    def new_profile(self, name: str, source=None) -> None:
        with self.lock:
            if self.profiles.exists(name):
                raise ApiError(409, f"a profile called {name!r} already exists")
            mods = self.profiles.load(source) if source else []
            self.profiles.save(name, mods)

    def rename_profile(self, name: str, to: str) -> dict:
        with self.lock:
            if not self.profiles.exists(name):
                raise ApiError(404, f"no profile called {name!r}")
            try:
                new = self.profiles.rename(name, to)
            except FileExistsError as ex:
                raise ApiError(409, str(ex))
            except ValueError as ex:
                raise ApiError(400, str(ex))
            if self.current == name:
                self.current = new
            if self.state.profile == name:
                self.state.profile = new
                self.state.save()
            return {"ok": True, "profile": self.current, "profiles": self.profiles.names()}

    def delete_profile(self, name: str) -> None:
        with self.lock:
            try:
                self.profiles.delete(name)
            except KeyError as ex:
                raise ApiError(404, str(ex))
            if self.current == name:
                rest = self.profiles.names()
                if rest:
                    self.select_profile(rest[0])
                else:
                    self.current, self.working = None, []

    # ------------------------------------------------------------ preview / apply
    def plan(self):
        with self.lock:
            return make_plan(self.cfg, self.library, list(self.working), self.state)

    def preview(self) -> dict:
        with self.lock:
            p = self.plan()
            warnings = self._warnings()
            pf = preflight(self.cfg, fresh=False)
            if pf["game_running"]:
                warnings.append("The game is running; close it before applying")
            if pf["vortex_running"]:
                warnings.append("Vortex is running; close it so it cannot change the game folder")
            warnings += [f"Blocked: {b['rel']} ({b['reason']})" for b in p.blocked]
            warnings += [f"Kept: {b['rel']} ({b['reason']})" for b in p.left]
            cap = 5000
            adds = [{"id": e.mod, "path": e.rel} for e in p.adds]
            rems = [{"id": r["mod"], "path": r["rel"]} for _, r in p.removes]
            return {"add": len(adds), "remove": len(rems), "conflicts": p.conflicts, "warnings": warnings,
                    "files": {"add": adds[:cap], "remove": rems[:cap]},
                    "filesTruncated": len(adds) > cap or len(rems) > cap}

    def need_game(self) -> None:
        """Changing the game folder only makes sense when it exists; say clearly what to do if it doesn't."""
        if not self.cfg.game_found:
            raise ApiError(409, f"Can't find Cyberpunk 2077 at “{self.cfg.game}”. Run CyberLoader Setup again and choose the "
                                "game folder (the one that contains bin\\x64\\Cyberpunk2077.exe).")

    def start_apply(self) -> None:
        with self.lock:
            if self.job["state"] == "running":
                raise ApiError(423, "another apply is already running")
            self.need_game()
            if preflight(self.cfg)["game_running"]:
                raise ApiError(409, "The game is running. Close it, then apply.")
            plan = self.plan()
            if plan.blocked:
                raise ApiError(409, f"{len(plan.blocked)} file(s) would overwrite something that is not from this manager, "
                                    f"for example {plan.blocked[0]['rel']}. Nothing was changed.")
            self.job = {"state": "running", "percent": 0, "text": "Starting"}
            profile = self.current
        threading.Thread(target=self._run_apply, args=(plan, profile), daemon=True).start()

    def _run_apply(self, plan, profile) -> None:
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        logf = open(self.cfg.logs_dir / f"apply-{stamp}.log", "w", encoding="utf-8")

        def log(m):
            logf.write(m + "\n")

        def progress(pct, text):
            self.job = {"state": "running", "percent": pct, "text": text}

        try:
            log(f"profile: {profile}; {plan.summary()}")
            res = apply_plan(self.cfg, plan, self.state, progress, log)
            self.state.profile = profile
            self.state.save()
            if res["errors"]:
                self.job = {"state": "error", "percent": 100, "text": f"{len(res['errors'])} problem(s); see logs\\apply-{stamp}.log"}
            else:
                self.job = {"state": "done", "percent": 100, "text": "Done"}
        except Exception as ex:  # keep the server alive; the log has the details
            log(f"FATAL {ex!r}")
            self.state.save()
            self.job = {"state": "error", "percent": 100, "text": str(ex)}
        finally:
            logf.close()

    def apply_blocking(self, progress=None, log=None) -> dict:
        """CLI use: apply the working set now."""
        self.need_game()
        plan = self.plan()
        if plan.blocked:
            raise ApiError(409, f"{len(plan.blocked)} blocked file(s), e.g. {plan.blocked[0]['rel']}")
        res = apply_plan(self.cfg, plan, self.state, progress, log)
        self.state.profile = self.current
        self.state.save()
        return res

    # ------------------------------------------------------------ import
    def import_path(self, path: str, name: str | None = None) -> dict:
        p = Path(path)
        if not p.exists():
            raise ApiError(404, f"not found: {path}")
        base = name or clean_name(p.stem if p.is_file() else p.name)
        mid, n = base, 2
        while (self.library.root / mid).exists():
            mid, n = f"{base} ({n})", n + 1
        try:
            with self.lock:
                mid, warns = self.library.import_sources([p], mid, self.cfg.tmp_dir)
        except (ValueError, RuntimeError, OSError) as ex:
            raise ApiError(400, str(ex))
        return {"ok": True, "id": mid, "warnings": warns}

    # ------------------------------------------------------------ deleting mods: an in-app trash
    # A deleted mod moves to <data>\trash\<time>-<rand>\mod (+ trash.json). Nothing is erased until the trash is emptied.
    _TRASH_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")

    @property
    def trash_root(self) -> Path:
        return self.cfg.data / "trash"

    def delete_mod(self, mod_id: str) -> dict:
        import shutil
        import uuid
        with self.lock:
            m = self.library.mods.get(mod_id)
            if m is None:
                raise ApiError(404, f"unknown mod: {mod_id}")
            if self.job["state"] == "running":
                raise ApiError(423, "another apply is running")
            if mod_id in self.state.deployed_mods():
                raise ApiError(409, f"“{m.name}” is in the game right now. Turn it off and apply first, then delete it.")
            folder = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
            dest = self.trash_root / folder
            dest.mkdir(parents=True)
            shutil.move(str(m.path), str(dest / "mod"))
            write_json(dest / "trash.json", {"id": m.id, "name": m.name, "group": m.group, "files": len(m.files),
                                             "size": m.size, "deletedAt": time.strftime("%Y-%m-%d %H:%M:%S")})
            del self.library.mods[mod_id]
            if mod_id in self.working:
                self.working.remove(mod_id)
            return {"ok": True, "trashId": folder, "name": m.name}

    def list_trash(self) -> dict:
        items = []
        if self.trash_root.exists():
            for d in sorted(self.trash_root.iterdir(), reverse=True):
                meta = read_json(d / "trash.json") if d.is_dir() and self._TRASH_ID.match(d.name) else None
                if meta:
                    items.append({"id": d.name, "name": meta.get("name", meta.get("id", d.name)), "group": meta.get("group", "Other"),
                                  "files": meta.get("files", 0), "size": meta.get("size", 0), "deletedAt": meta.get("deletedAt", "")})
        return {"items": items, "totalSize": sum(i["size"] for i in items)}

    def _trash_item(self, trash_id: str) -> Path:
        if not self._TRASH_ID.match(trash_id or ""):
            raise ApiError(400, "not a trash item")
        d = self.trash_root / trash_id
        if not d.is_dir():
            raise ApiError(404, "that item is no longer in the trash")
        return d

    def restore_trash(self, trash_id: str) -> dict:
        import shutil
        with self.lock:
            d = self._trash_item(trash_id)
            meta = read_json(d / "trash.json") or {}
            base = str(meta.get("id") or d.name)
            new_id, n = base, 1
            while (self.library.root / new_id).exists():
                n += 1
                new_id = f"{base} (restored)" if n == 2 else f"{base} (restored {n - 1})"
            shutil.move(str(d / "mod"), str(self.library.root / new_id))
            shutil.rmtree(d, ignore_errors=True)
            self.library.mods[new_id] = self.library._load(self.library.root / new_id)
            return {"ok": True, "id": new_id, "name": self.library.mods[new_id].name}

    def empty_trash(self, trash_id=None) -> dict:
        import shutil
        import stat

        def _force(func, path, _exc):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        with self.lock:
            targets = [self._trash_item(trash_id)] if trash_id else (
                [d for d in self.trash_root.iterdir() if d.is_dir() and self._TRASH_ID.match(d.name)] if self.trash_root.exists() else [])
            freed = 0
            for d in targets:
                meta = read_json(d / "trash.json") or {}
                freed += int(meta.get("size", 0))
                shutil.rmtree(d, onexc=_force)
            return {"ok": True, "removed": len(targets), "freed": freed}

    # ------------------------------------------------------------ import by upload (drag and drop)
    MAX_UPLOAD_BYTES = 8 << 30
    MAX_UPLOAD_FILES = 50000

    def import_begin(self, name: str, kind: str) -> dict:
        import uuid
        name = (name or "").strip()
        if kind not in ("archive", "folder"):
            raise ApiError(400, "kind must be 'archive' or 'folder'")
        if not name:
            raise ApiError(400, "name is required")
        token = uuid.uuid4().hex
        d = self.cfg.tmp_dir / f"upload-{token}"
        d.mkdir(parents=True)
        with self.lock:
            self.uploads[token] = {"name": name, "kind": kind, "dir": d, "bytes": 0, "files": 0}
        return {"token": token}

    def import_target(self, token: str, path: str):
        """Validate an upload path and return (upload record, destination file). Never allows leaving the upload folder."""
        import re
        from .library import ARCHIVE_EXT
        with self.lock:
            up = self.uploads.get(token)
        if up is None:
            raise ApiError(404, "unknown or finished upload")
        raw = (path or "").replace("\\", "/")
        parts = [p for p in raw.split("/") if p not in ("", ".")]
        if (not parts or raw.startswith("/") or re.match(r"^[A-Za-z]:", parts[0])
                or any(p == ".." or re.search(r'[<>:"|?*\x00-\x1f]', p) for p in parts)):
            raise ApiError(400, f"unsafe path: {path!r}")
        if up["kind"] == "archive":
            parts = parts[-1:]
            if Path(parts[0]).suffix.lower() not in ARCHIVE_EXT:
                raise ApiError(400, "only .zip, .7z and .rar archives can be imported")
            if up["files"] >= 1:
                raise ApiError(400, "an archive import takes exactly one file")
        elif up["files"] >= self.MAX_UPLOAD_FILES:
            raise ApiError(413, "too many files in one import")
        dest = up["dir"].joinpath(*parts)
        try:
            dest.resolve().relative_to(up["dir"].resolve())
        except ValueError:
            raise ApiError(400, f"unsafe path: {path!r}")
        return up, dest

    def import_finish(self, token: str) -> dict:
        import shutil
        with self.lock:
            up = self.uploads.pop(token, None)
        if up is None:
            raise ApiError(404, "unknown or finished upload")
        try:
            files = [p for p in up["dir"].rglob("*") if p.is_file()]
            if not files:
                raise ApiError(400, "nothing was uploaded")
            if up["kind"] == "archive":
                sources = [files[0]]
                base = clean_name(Path(up["name"]).stem)
            else:
                sources = [up["dir"]]
                base = clean_name(up["name"])
            mid, n = base, 2
            while (self.library.root / mid).exists():
                mid, n = f"{base} ({n})", n + 1
            try:
                with self.lock:
                    mid, warns = self.library.import_sources(sources, mid, self.cfg.tmp_dir)
            except (ValueError, RuntimeError, OSError) as ex:
                raise ApiError(400, str(ex))
            return {"ok": True, "id": mid, "warnings": warns}
        finally:
            shutil.rmtree(up["dir"], ignore_errors=True)

    # ------------------------------------------------------------ Vortex adoption
    def adopt_vortex(self, manifest: Path, staging: Path | None = None, profile_name="Vortex import",
                     clone=True, log=print) -> dict:
        """Take over what Vortex deployed: hardlink-clone its staging folder into our library (no extra disk space,
        Vortex is left untouched), record every deployed file in our state, and save the set as a profile."""
        if self.state.files:
            raise ApiError(409, "state already holds deployed files; refusing to overwrite it")
        m = msgpack_min.loads(Path(manifest).read_bytes())
        staging = Path(staging or m["stagingPath"])
        target = Path(m["targetPath"])
        if target.resolve() != self.cfg.game.resolve():
            raise ApiError(400, f"manifest is for {target}, but the game is {self.cfg.game}")
        if clone:
            n = 0
            for d in sorted(staging.iterdir()):
                if not d.is_dir() or d.name.startswith(("__", "collection_")):
                    continue
                dest = self.library.root / d.name
                if dest.exists():
                    continue
                n += clone_tree(d, dest)
            log(f"cloned {n} files from {staging} into {self.library.root}")
            self.library.scan()
        owners: dict = {}
        files = m["files"]
        missing = 0
        for f in files:
            rel, mod = f["relPath"], f["source"]
            dst = self.cfg.game / rel
            try:
                st = os.stat(dst)
            except FileNotFoundError:
                missing += 1
                continue
            src = self.library.root / mod / rel
            try:
                same = os.path.samefile(src, dst)
            except OSError:
                same = False
            self.state.files[key(rel)] = {"rel": rel, "mod": mod, "mode": "link" if same else "copy",
                                          "size": st.st_size, "mtime_ns": st.st_mtime_ns, "ino": st.st_ino}
            owners[key(rel)] = mod
        order = order_for_owners(self.library, sorted({r["mod"] for r in self.state.files.values()}), owners)
        self.profiles.save(profile_name, order)
        self.state.profile = profile_name
        self.state.save()
        self.current = profile_name
        self.profiles.set_current(profile_name)
        self.working = order
        return {"files": len(self.state.files), "missing": missing, "mods": len(order)}


def clone_tree(src: Path, dst: Path) -> int:
    n = 0
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        if p.is_dir():
            (dst / rel).mkdir(parents=True, exist_ok=True)
        else:
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(p, dst / rel)
            except OSError:
                import shutil
                shutil.copy2(p, dst / rel)
            n += 1
    if not dst.exists():
        dst.mkdir(parents=True)
    return n


def order_for_owners(library: Library, ids: list, owners: dict) -> list:
    """Order mods so that, wherever two overlap, the one that owned the file on disk comes last (wins)."""
    after: dict = {i: set() for i in ids}   # mod -> mods that must come after it
    indeg: dict = {i: 0 for i in ids}
    by_key: dict = {}
    for i in ids:
        for k in library.mods[i].files if i in library.mods else []:
            by_key.setdefault(k, []).append(i)
    for k, mods in by_key.items():
        if len(mods) < 2 or k not in owners:
            continue
        win = owners[k]
        for loser in mods:
            if loser != win and win in after and win not in after[loser]:
                after[loser].add(win)
                indeg[win] += 1
    out, ready = [], sorted([i for i in ids if indeg[i] == 0], key=str.lower)
    while ready:
        i = ready.pop(0)
        out.append(i)
        for n in sorted(after[i], key=str.lower):
            indeg[n] -= 1
            if indeg[n] == 0:
                ready.append(n)
    return out + [i for i in ids if i not in out]  # cycle fallback: keep the rest
