"""Save transfer: copy parts of a Cyberpunk 2077 character (gender, look, clothes, outfits, guns) from one save to another.

The work is done by an optional add-on (`<data>\\addons\\savetool`, built from addons/savetool on top of the MIT-licensed
CP2077SaveEditor). The engine only decides what is allowed and keeps everything safe:
  - never when the game is running;
  - the two saves involved are copied to `<data>\\save-backups\\<time>\\` first;
  - the add-on writes into a temporary folder; the result is checked and then put into the game's saves folder as a NEW
    slot (`ManualSave-<next free number>`). Existing saves are never changed, moved or deleted.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .deploy import game_running
from .util import CREATE_NO_WINDOW, read_json, write_json

SLOT_FILES = ("sav.dat", "metadata.9.json", "screenshot.png")
SAFE_SLOT = re.compile(r"^[A-Za-z0-9 ._-]{1,80}$")
HELPER_TIMEOUT = 240


class TransferError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_KINDS = (("manual", "Manual save"), ("auto", "Autosave"), ("quick", "Quicksave"))


def _kind(name: str):
    """("manual"|"auto"|"quick"|"other", number or None) from a save folder name like ManualSave-34."""
    for kind, _ in _KINDS:
        m = re.fullmatch(kind + r"save-(\d+)", name, re.I)
        if m:
            return kind, int(m.group(1))
    return "other", None


def _label(name: str, kind: str, number) -> str:
    for k, text in _KINDS:
        if k == kind and number is not None:
            return f"{text} {number}"
    return name


class SaveTransfer:
    def __init__(self, cfg, helper_cmd=None, helper_env=None):
        self.cfg = cfg
        self._helper_cmd = helper_cmd      # tests: a command list that behaves like the add-on
        self._helper_env = helper_env or {}
        self._inspected = {}      # (save name, size, mtime) -> inspect answer: opening a save takes ~15 s, so ask once per version of a save

    # ------------------------------------------------------------ the add-on
    def addon_dir(self) -> Path:
        return self.cfg.addons_dir / "savetool"

    def _command(self):
        """The command that runs the add-on, or (None, why not)."""
        if self._helper_cmd:
            return list(self._helper_cmd), None
        d = self.addon_dir()
        if not (d / "editor" / "CP2077SaveEditor.dll").is_file():
            return None, "The save transfer add-on is not installed."
        exe, dll = d / "savetool.exe", d / "savetool.dll"
        if exe.is_file():
            return [str(exe)], None
        if dll.is_file():
            dotnet = shutil.which("dotnet") or r"C:\Program Files\dotnet\dotnet.exe"
            if Path(dotnet).is_file():
                return [dotnet, str(dll)], None
            return None, "The save transfer add-on needs the .NET 10 Desktop Runtime, which was not found."
        return None, "The save transfer add-on is not installed."

    def available(self) -> tuple:
        cmd, why = self._command()
        return cmd is not None, why

    def _run_helper(self, args: list) -> dict:
        cmd, why = self._command()
        if cmd is None:
            raise TransferError(409, why)
        env = dict(os.environ)
        env["CP2077_EDITOR_DIR"] = str(self.addon_dir() / "editor")
        env.update(self._helper_env)
        try:
            p = subprocess.run(cmd + args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=HELPER_TIMEOUT, env=env, creationflags=CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired:
            raise TransferError(504, "The save tool took too long, so it was stopped. Nothing was changed.")
        except OSError as ex:
            raise TransferError(500, f"The save tool could not be started: {ex}")
        lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip().startswith("{")]
        try:
            out = json.loads(lines[-1]) if lines else None
        except ValueError:
            out = None
        if not out:
            tail = (p.stderr or p.stdout or "").strip().splitlines()[-1:] or ["no answer"]
            raise TransferError(500, f"The save tool gave no usable answer ({tail[0][:200]}). Nothing was changed.")
        if not out.get("ok"):
            raise TransferError(409, str(out.get("error") or "The save tool refused."))
        return out

    # ------------------------------------------------------------ saves
    def _slot_dir(self, name: str) -> Path:
        if not isinstance(name, str) or not SAFE_SLOT.match(name) or name in (".", ".."):
            raise TransferError(400, "Pick a save from the list.")
        d = self.cfg.saves_dir / name
        if not (d / "sav.dat").is_file():
            raise TransferError(404, f"Can’t find the save “{name}”.")
        return d

    @staticmethod
    def _slot_info(d: Path) -> dict:
        meta = {}
        try:
            meta = (read_json(d / "metadata.9.json", {}) or {}).get("Data", {}).get("metadata", {}) or {}
        except (OSError, ValueError):
            pass
        try:
            mtime = (d / "sav.dat").stat().st_mtime
        except OSError:
            mtime = 0
        play = meta.get("playTime")
        kind, number = _kind(d.name)
        return {"id": d.name, "kind": kind, "label": _label(d.name, kind, number), "bodyGender": meta.get("bodyGender"), "voice": meta.get("brainGender"),
                "level": int(meta["level"]) if isinstance(meta.get("level"), (int, float)) else None,
                "hours": round(play / 3600, 1) if isinstance(play, (int, float)) else None,
                "lifePath": meta.get("lifePath"), "modded": bool(meta.get("isModded")) if "isModded" in meta else None,
                "playthrough": meta.get("playthroughID"), "savedAt": int(mtime),
                "patch": meta.get("buildPatch"), "hasPicture": (d / "screenshot.png").is_file()}

    def list_view(self) -> dict:
        ok, why = self.available()
        out = {"available": ok, "reason": why, "savesDir": str(self.cfg.saves_dir), "saves": [], "playthroughs": [],
               "gameRunning": game_running()}
        if ok and self.cfg.saves_dir.is_dir():
            for d in self.cfg.saves_dir.iterdir():
                if d.is_dir() and (d / "sav.dat").is_file():
                    out["saves"].append(self._slot_info(d))
            out["saves"].sort(key=lambda s: s["savedAt"], reverse=True)
            out["playthroughs"] = self._playthroughs(out["saves"])
        elif ok:
            out["reason"] = f"The saves folder was not found: {self.cfg.saves_dir}"
        return out

    # ------------------------------------------------------------ playthroughs (the game files saves under a playthrough id)
    def _names_file(self) -> Path:
        return self.cfg.data / "save-names.json"

    def _names(self) -> dict:
        try:
            n = read_json(self._names_file(), {}) or {}
            return {str(k): str(v) for k, v in n.items()} if isinstance(n, dict) else {}
        except (OSError, ValueError):
            return {}

    def _playthroughs(self, saves: list) -> list:
        """Saves (given newest first) grouped by playthrough id, the most recently played playthrough first. Each group lists its save ids, newest first."""
        names = self._names()
        groups = {}
        for sv in saves:
            groups.setdefault(sv["playthrough"] or "unknown", []).append(sv)
        out = []
        for pid, items in groups.items():
            hours = [x["hours"] for x in items if x["hours"] is not None]
            out.append({"id": pid, "name": names.get(pid), "count": len(items), "first": min(x["savedAt"] for x in items),
                        "last": max(x["savedAt"] for x in items), "bodies": sorted({x["bodyGender"] for x in items if x["bodyGender"]}),
                        "level": items[0]["level"], "hours": max(hours) if hours else None, "saves": [x["id"] for x in items]})
        out.sort(key=lambda g: g["last"], reverse=True)
        return out

    def set_name(self, playthrough: str, name) -> dict:
        """Give a playthrough a name of your own (or clear it with an empty name). Only this app's own names file changes."""
        pid = str(playthrough or "")
        known = {g["id"] for g in self._playthroughs([self._slot_info(d) for d in self.cfg.saves_dir.iterdir()
                                                       if d.is_dir() and (d / "sav.dat").is_file()])} if self.cfg.saves_dir.is_dir() else set()
        if pid not in known:
            raise TransferError(404, "Can’t find that playthrough.")
        text = " ".join(str(name or "").split())[:60]
        names = self._names()
        if text:
            names[pid] = text
        else:
            names.pop(pid, None)
        try:
            write_json(self._names_file(), names)
        except OSError as ex:
            raise TransferError(500, f"Couldn’t save the name ({ex}).")
        return {"ok": True, "id": pid, "name": text or None}

    def inspect(self, save: str) -> dict:
        d = self._slot_dir(save)
        try:
            st = (d / "sav.dat").stat()
            key = (save, st.st_size, st.st_mtime_ns)
        except OSError:
            key = None
        if key and key in self._inspected:
            return dict(self._inspected[key])
        r = self._run_helper(["inspect", str(d)])
        out = {"id": save, "bodyGender": r.get("bodyGender"), "voice": r.get("voice"), "counts": r.get("counts", {})}
        if key:
            self._inspected = {k: v for k, v in self._inspected.items() if k[0] != save}     # only the newest version of a save is kept
            self._inspected[key] = out
        return dict(out)

    # ------------------------------------------------------------ transfer
    @staticmethod
    def _options(body: dict) -> list:
        gender = str(body.get("gender") or "keep").lower()
        if gender not in ("keep", "female", "male"):
            raise TransferError(400, "gender must be keep, female or male")
        args = ["--gender", gender]
        picked = gender != "keep"
        for key, flag in (("look", "--look"), ("clothes", "--clothes"), ("outfits", "--outfits"), ("guns", "--guns"), ("tidy", "--tidy"), ("stripMods", "--strip-mods")):
            if body.get(key):
                args.append(flag)
                picked = True
        money = body.get("money")
        if money is not None and money != "":
            try:
                n = int(str(money).strip().replace(",", ""))
            except ValueError:
                raise TransferError(400, "Money has to be a whole number, like 25000.")
            if not 0 <= n <= 2_000_000_000:
                raise TransferError(400, "Money has to be between 0 and 2,000,000,000.")
            args += ["--money", str(n)]
            picked = True
        if not picked:
            raise TransferError(400, "Tick at least one thing to transfer.")
        return args

    def _check(self, body: dict):
        """(source folder or None, target folder, option arguments). A gender change alone needs no source save."""
        src, dst = body.get("source"), body.get("target")
        opts = self._options(body)
        t = self._slot_dir(dst)
        s = None
        if any(body.get(k) for k in ("look", "clothes", "outfits", "guns")):
            s = self._slot_dir(src)
            if src == dst:
                raise TransferError(400, "The two saves have to be different.")
        return s, t, opts

    @staticmethod
    def _src_args(s) -> list:
        return ["--source", str(s)] if s else []

    def preview(self, body: dict) -> dict:
        s, t, opts = self._check(body)
        r = self._run_helper(["transfer"] + self._src_args(s) + ["--target", str(t), "--dry-run"] + opts)
        return {"ok": True, "report": r.get("report", {})}

    def _next_slot(self) -> str:
        top = 0
        for d in self.cfg.saves_dir.iterdir():
            m = re.fullmatch(r"ManualSave-(\d+)", d.name)
            if m:
                top = max(top, int(m.group(1)))
        return f"ManualSave-{top + 1}"

    def run(self, body: dict) -> dict:
        s, t, opts = self._check(body)
        if game_running(fresh=True):
            raise TransferError(409, "The game is running. Close it first (a running game can overwrite saves).")
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        backup = self.cfg.save_backups_dir / stamp
        for d in [x for x in (s, t) if x]:
            dst = backup / d.name
            dst.mkdir(parents=True, exist_ok=True)
            for f in SLOT_FILES:
                if (d / f).is_file():
                    shutil.copy2(d / f, dst / f)
            if not (dst / "sav.dat").is_file() or _sha(dst / "sav.dat") != _sha(d / "sav.dat"):
                raise TransferError(500, "Couldn’t make a backup copy of the saves, so nothing was changed.")
        work = self.cfg.tmp_dir / f"transfer-{stamp}"
        out_dir = work / "out"
        try:
            r = self._run_helper(["transfer"] + self._src_args(s) + ["--target", str(t), "--out", str(out_dir)] + opts)
            if not (out_dir / "sav.dat").is_file() or (out_dir / "sav.dat").stat().st_size < 1000:
                raise TransferError(500, "The save tool did not produce a save. Nothing was changed.")
            slot = self._next_slot()
            dest = self.cfg.saves_dir / slot
            os.mkdir(dest)      # fails if it exists: an existing save is never reused
            try:
                for f in SLOT_FILES:
                    if (out_dir / f).is_file():
                        shutil.copy2(out_dir / f, dest / f)
                if _sha(dest / "sav.dat") != _sha(out_dir / "sav.dat"):
                    raise OSError("the copy in the saves folder does not match")
            except OSError as ex:
                shutil.rmtree(dest, ignore_errors=True)     # our own half-made folder, never an existing save
                raise TransferError(500, f"Couldn’t put the new save in the saves folder ({ex}). Nothing was changed.")
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return {"ok": True, "slot": slot, "report": r.get("report", {}), "result": r.get("result", {}),
                "backup": str(backup), "source": s.name if s else None, "target": t.name,
                "playthrough": self._slot_info(dest).get("playthrough")}
