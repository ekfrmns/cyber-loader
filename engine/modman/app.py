"""Application layer shared by the CLI and the local API server."""
import os
import re
import threading
import time
from pathlib import Path

from . import __version__, msgpack_min
from .config import NOT_SET, Config, check_game_folder
from .deploy import (Entry, Plan, State, _identical, _stat, apply_plan, build_desired, conflict_counts, game_running,
                     intact, make_plan, preflight)
from .library import GROUPS, Library, clean_name, normalize_root
from .profiles import Profiles
from .savetransfer import SaveTransfer, TransferError
from .snapshots import Snapshots, describe, parse_origin, pretty_version
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
        self.snapshots = Snapshots(cfg.snapshots_dir)
        self.savetransfer = SaveTransfer(cfg)
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
            others = self.library.other_versions()
            for m in self.library.mods.values():
                v = self._mod_view(m, enabled, deployed, cc, self.library.auto_requires(m, providers), others.get(m.id))
                if v["pending"] == "on":
                    on += 1
                elif v["pending"] == "off":
                    off += 1
                mods.append(v)
            return {"game": {"running": game_running(), "found": self.cfg.game_found, **self.cfg.game_info()}, "profile": self.current,
                    "profiles": self.profiles.names(), "deployedCount": len(self.state.files),
                    "pendingCount": {"on": on, "off": off}, "profileDirty": self._profile_dirty(),
                    "version": __version__, "saveTransfer": self.savetransfer.available()[0], "mods": mods}

    @staticmethod
    def _mod_view(m, enabled: set, deployed: set, cc: dict, auto=None, others=None) -> dict:
        pending = None
        if m.id in enabled and m.id not in deployed:
            pending = "on"
        elif m.id not in enabled and m.id in deployed:
            pending = "off"
        return {"id": m.id, "name": m.name, "group": m.group, "files": len(m.files), "enabled": m.id in enabled,
                "pending": pending, "framework": m.framework, "requires": m.requires, "autoRequires": auto or [], "conflicts": cc.get(m.id, 0),
                "nexusId": m.nexus_id, "version": m.version, "uploaded": m.uploaded, "otherVersions": others or []}

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
        others = self.library.other_versions()
        for mid in self.working:
            m = self.library.mods[mid]
            for r in m.requires:
                if r not in enabled:
                    rn = self.library.mods[r].name if r in self.library.mods else r
                    items.append((mid, [r], f"{m.name} needs {rn}, which is off"))
            for oid in others.get(mid, []):                          # another version of this same mod is on too
                if oid in enabled:
                    a, b = sorted((m.name, self.library.mods[oid].name))   # same wording from both sides, so it is listed once
                    items.append((mid, [oid], f"“{a}” and “{b}” look like two versions of the same mod. Turn one of them off"))
            for need in self.library.auto_requires(m, providers):   # guessed from the mod's files
                if any(i in enabled for i in need["ids"]):
                    continue
                why = "which is off" if need["ids"] else "which is not in your library"
                items.append((mid, need["ids"], f"{m.name} needs {need['name']}, {why}"))
        return items

    def _warnings(self) -> list:
        return list(dict.fromkeys(text for _, _, text in self._warning_items()))   # each text once (a pair is listed from both sides)

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
                                  self.library.auto_requires(self.library.mods[mod_id]), self.library.other_versions().get(mod_id))
            return {"ok": True, "mod": view, "warnings": sorted(set(warns))}

    def set_requires(self, mod_id: str, requires) -> dict:
        """Set the mods that `mod_id` needs (the hand-made list). Only the mod's own `.mod.json` changes, never the game."""
        with self.lock:
            m = self.library.mods.get(mod_id)
            if m is None:
                raise ApiError(404, f"unknown mod: {mod_id}")
            if not isinstance(requires, list) or not all(isinstance(r, str) for r in requires):
                raise ApiError(400, "requires must be a list of mod ids")
            clean = []
            for r in requires:
                if r == mod_id:
                    raise ApiError(400, f"“{m.name}” cannot need itself")
                if r not in self.library.mods:
                    raise ApiError(400, f"unknown mod: {r}")
                if r not in clean:
                    clean.append(r)
            self.library.write_meta(mod_id, requires=clean)
            m.requires = clean
            _, conflicts = build_desired(self.library, self.working)
            view = self._mod_view(m, set(self.working), self.state.deployed_mods(), conflict_counts(conflicts),
                                  self.library.auto_requires(m), self.library.other_versions().get(m.id))
            return {"ok": True, "mod": view, "warnings": sorted({t for mid, _, t in self._warning_items() if mid == mod_id})}

    def set_group(self, mod_id: str, group: str) -> dict:
        """Move a mod to a category. Saved in the mod's own `.mod.json`, so the name-based guess never overrides it again."""
        with self.lock:
            m = self.library.mods.get(mod_id)
            if m is None:
                raise ApiError(404, f"unknown mod: {mod_id}")
            if group not in GROUPS:
                raise ApiError(400, f"category must be one of: {', '.join(GROUPS)}")
            self.library.write_meta(mod_id, group=group, framework=(group == "Framework"))
            m.group, m.framework = group, group == "Framework"
            _, conflicts = build_desired(self.library, self.working)
            view = self._mod_view(m, set(self.working), self.state.deployed_mods(), conflict_counts(conflicts), self.library.auto_requires(m),
                                  self.library.other_versions().get(m.id))
            return {"ok": True, "mod": view}

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
            ids = list(self.working)
        threading.Thread(target=self._run_apply, args=(plan, profile, ids), daemon=True).start()

    def _run_apply(self, plan, profile, ids=None) -> None:
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
                self._auto_snapshot(ids, profile, log)
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
        if not res.get("errors"):
            self._auto_snapshot(list(self.working), self.current)
        return res

    # ------------------------------------------------------------ setup history (snapshots)
    def _snapshot_mods(self, ids) -> list:
        return [describe(self.library.mods[i]) for i in ids if i in self.library.mods]

    def _auto_snapshot(self, ids, profile, log=None) -> None:
        """After a good apply: remember this setup. Never lets a problem here break the apply."""
        try:
            mods = self._snapshot_mods(ids or [])
            if not self.snapshots.same_as_latest(mods, profile):
                self.snapshots.save(mods, profile, auto=True)
        except Exception as ex:
            if log:
                log(f"snapshot not saved: {ex!r}")

    def _changed_since(self, m: dict) -> bool:
        cur = self.library.mods.get(m["id"])
        return cur is not None and (len(cur.files) != m.get("files") or cur.size != m.get("size"))

    def list_snapshots(self) -> dict:
        with self.lock:
            now = set(self.working)
            items = []
            for s in self.snapshots.all():
                ids = [m["id"] for m in s["mods"]]
                items.append({"id": s["id"], "at": s["at"], "profile": s.get("profile"), "auto": bool(s.get("auto")),
                              "pinned": bool(s.get("pinned")), "name": s.get("name"), "count": len(ids),
                              "turnOn": sum(1 for i in ids if i not in now and i in self.library.mods),
                              "turnOff": len(now - set(ids)),
                              "missing": sum(1 for i in ids if i not in self.library.mods),
                              "changed": sum(1 for m in s["mods"] if self._changed_since(m))})
            return {"items": items}

    def _trash_ids(self) -> dict:
        """mod id -> trash id for every mod currently in the in-app trash."""
        out = {}
        if self.trash_root.exists():
            for d in self.trash_root.iterdir():
                meta = read_json(d / "trash.json") if d.is_dir() and self._TRASH_ID.match(d.name) else None
                if meta and meta.get("id"):
                    out[meta["id"]] = d.name
        return out

    def get_snapshot(self, sid: str) -> dict:
        """One snapshot with, for each mod, how it compares to the library now (same / changed / missing)."""
        with self.lock:
            try:
                s = self.snapshots.load(sid)
            except KeyError as ex:
                raise ApiError(404, str(ex).strip("'\""))
            now = set(self.working)
            trash = self._trash_ids()
            by_nexus: dict = {}
            for m in self.library.mods.values():
                n = parse_origin(m.id).get("nexusId")
                if n:
                    by_nexus.setdefault(n, []).append(m)
            mods = []
            for m in s["mods"]:
                row = {k: m.get(k) for k in ("id", "name", "version", "date", "nexusId")}
                row["version"] = pretty_version(parse_origin(m["id"])) or row["version"]   # "2-0-1" is shown as "2.0.1"
                row["on"] = m["id"] in now
                if m["id"] not in self.library.mods:
                    row["status"] = "missing"
                    row["inTrash"] = m["id"] in trash
                    # the same Nexus mod under another folder = the updated version
                    repl = [x for x in by_nexus.get(m.get("nexusId"), []) if x.id != m["id"]]
                    if repl:
                        row["replacedBy"] = {"id": repl[0].id, "name": repl[0].name, "version": repl[0].version, "date": repl[0].uploaded}
                else:
                    row["status"] = "changed" if self._changed_since(m) else "same"
                mods.append(row)
            return {"id": s["id"], "at": s["at"], "profile": s.get("profile"), "auto": bool(s.get("auto")),
                    "pinned": bool(s.get("pinned")), "name": s.get("name"), "mods": mods}

    def save_snapshot(self, name: str = "") -> dict:
        """Keep the mods that are on right now (the staged set) under a name. Named snapshots are never cleaned up."""
        with self.lock:
            sid = self.snapshots.save(self._snapshot_mods(self.working), self.current, auto=False, name=name)
            self.snapshots.pin(sid, True)
            return {"ok": True, "id": sid}

    def pin_snapshot(self, sid: str, pinned: bool, name=None) -> dict:
        with self.lock:
            try:
                d = self.snapshots.pin(sid, pinned, name)
            except KeyError as ex:
                raise ApiError(404, str(ex).strip("'\""))
            return {"ok": True, "pinned": d["pinned"], "name": d["name"]}

    def restore_snapshot(self, sid: str) -> dict:
        """Stage an older setup: the mod list becomes exactly that one (mods no longer in the library are skipped and named).
        Nothing in the game changes until the usual Review and Apply."""
        with self.lock:
            if self.job["state"] == "running":
                raise ApiError(423, "another apply is running")
            try:
                s = self.snapshots.load(sid)
            except KeyError as ex:
                raise ApiError(404, str(ex).strip("'\""))
            self.working = [m["id"] for m in s["mods"] if m["id"] in self.library.mods]
            view = self.state_view()
            view["restored"] = {"count": len(self.working),
                                "missing": [{k: m.get(k) for k in ("name", "version", "date", "nexusId")}
                                            for m in s["mods"] if m["id"] not in self.library.mods],
                                "changed": sum(1 for m in s["mods"] if self._changed_since(m))}
            return view

    # ------------------------------------------------------------ game folder (changeable after install)
    def _game_block_reason(self, fresh: bool):
        """Why the game folder can't be changed right now, in plain words, or None. Order: what never changes, then what
        is happening now, then what is in the game folder."""
        why = self.cfg.game_locked_reason()
        if why:
            return why
        if self.job["state"] == "running":
            return "An apply is running. Wait for it to finish, then change the folder."
        if (preflight(self.cfg) if fresh else {"game_running": game_running()})["game_running"]:
            return "The game is running. Close it, then change the folder."
        if self.state.files:
            return ("Some mods are still placed in the current game folder. Turn everything off and apply first, "
                    "then change the folder.")
        return None

    def game_folder(self) -> dict:
        with self.lock:
            found = self.cfg.game_found
            return {"path": None if self.cfg.game == NOT_SET else str(self.cfg.game), "found": found,
                    **(self.cfg.game_info() if found else {}), "deployedCount": len(self.state.files),
                    "canChange": (reason := self._game_block_reason(False)) is None, "reason": reason}

    def check_game_folder(self, path) -> dict:
        """Say what is at this path (nothing is changed). `same` = it is the folder in use already."""
        out = check_game_folder(path)
        out["same"] = bool(out["found"] and self.cfg.game != NOT_SET
                           and os.path.normcase(os.path.normpath(out["path"])) == os.path.normcase(os.path.normpath(str(self.cfg.game))))
        return out

    def set_game_folder(self, path) -> dict:
        """Use another game folder from now on. Only the settings file (and the engine's own records) change: nothing is
        copied, moved or deleted in either game folder. Refused while anything is placed in the old folder (state\\deployed.json
        records files relative to it), while the game runs, or while an apply runs."""
        with self.lock:
            chk = check_game_folder(path)
            if not chk["found"]:
                raise ApiError(400, chk["message"])
            reason = self._game_block_reason(True)
            if reason:
                raise ApiError(423 if self.job["state"] == "running" else 409, reason)
            if self.check_game_folder(path)["same"]:
                return {"ok": True, "changed": False, **self.game_folder()}
            try:
                self.cfg.save_game(Path(chk["path"]))
            except (OSError, ValueError) as ex:
                raise ApiError(500, f"Couldn’t save the new game folder, so nothing changed. {ex}")
            # Nothing is placed any more, so these records only described the old folder: drop them so they can never be
            # matched against the new one. (Records only; no file or folder is touched.)
            if self.state.dirs or self.state.left:
                self.state.dirs, self.state.left = [], set()
                try:
                    self.state.save()
                except OSError:
                    pass        # the folder is already changed; these records are only tidiness, so do not report a failure
            return {"ok": True, "changed": True, **self.game_folder()}

    # ------------------------------------------------------------ save transfer (optional add-on)
    def savetransfer_view(self) -> dict:
        return self.savetransfer.list_view()

    def savetransfer_call(self, what: str, body: dict) -> dict:
        """what: inspect | name | preview | run. Errors from the add-on layer become API errors with a plain message."""
        try:
            if what == "inspect":
                return self.savetransfer.inspect(str(body.get("save") or ""))
            if what == "name":
                return self.savetransfer.set_name(body.get("playthrough"), body.get("name"))
            if what == "preview":
                return self.savetransfer.preview(body)
            if what == "run":
                with self.lock:
                    if self.job["state"] == "running":
                        raise ApiError(423, "An apply is running. Wait for it to finish first.")
                return self.savetransfer.run(body)
        except TransferError as ex:
            raise ApiError(ex.code, ex.message)
        raise ApiError(404, "unknown endpoint")

    # ------------------------------------------------------------ import
    def import_path(self, path: str, name: str | None = None) -> dict:
        p = Path(path)
        if not p.exists():
            raise ApiError(404, f"not found: {path}")
        base = name or (p.stem if p.is_file() else p.name)   # keep the original name: the Nexus number, version and date stay readable
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
                base = Path(up["name"]).stem
            else:
                sources = [up["dir"]]
                base = up["name"]
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
