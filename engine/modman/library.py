"""The mod library: one folder per mod, each laid out exactly like the game folder."""
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .util import CREATE_NO_WINDOW, find_7z, key, norm_rel, read_json, write_json

META = ".mod.json"
GAME_ROOTS = {"archive", "bin", "engine", "r6", "red4ext", "mods", "tools"}
ARCHIVE_EXT = {".zip", ".7z", ".rar"}

# ---------------------------------------------------------------- names and groups
_RE_NEXUS = re.compile(r"\s+\d{3,6}\s+[\dv][\w.\-]*\s+\d{4}-\d\d-\d\dT[\w-]+Z\s+\w+$")
_RE_NEXUS_OLD = re.compile(r"-\d{3,6}-[\w-]*-\d{9,}$")

_FRAMEWORK = re.compile(
    r"^(red4ext|redscript|codeware|archivexl|tweakxl|cet\b|cyber engine tweaks|mod settings|input loader|"
    r"audioware|native settings|reddata|redfilesystem|red file system|simple video framework|"
    r"custom map markers|native interactions framework|browserextensionframework|appearance runtime|"
    r"equipment-ex|cyberware-ex|virtual atelier$)", re.I)
_GROUP_RULES = [
    ("Body", re.compile(r"body|sp0|vtk|texture|physics|\blod\b|microdetail|reflections|palette|jiggle", re.I)),
    ("Clothing", re.compile(r"dress|boots|jacket|suit|necklace|jewelry|pants|shirt|holster|atelier|\btags\b|bodysuit|bomber|fashion", re.I)),
    ("Gameplay", re.compile(r"cyberware|craft|weapon|silenc|knives|newgame|new game|sandevistan|first person|stats|upgrade|"
                            r"sell apartments|jump|airdrop|cyberpsycho|unequip|intro videos|"
                            r"vehicle|camo|lod tweak", re.I)),
    ("Characters", re.compile(r"fomod|supporting npc|hologram|npc", re.I)),
    ("Content", re.compile(r"encounter|quest|braindance|advert|loading screen|"
                           r"penthouse|apartment", re.I)),
]


def clean_name(folder: str) -> str:
    s = _RE_NEXUS.sub("", folder)
    s = _RE_NEXUS_OLD.sub("", s)
    return s.strip(" -") or folder


def guess_group(name: str) -> str:
    if _FRAMEWORK.search(name.strip()):
        return "Framework"
    for group, rx in _GROUP_RULES:
        if rx.search(name):
            return group
    return "Other"


# ---------------------------------------------------------------- frameworks guessed from files
# A mod that ships a file of a certain kind needs the framework that reads it (a `.reds` script needs Redscript, an
# `.xl` file needs ArchiveXL, ...). A mod IS that framework when it ships the framework's own files. Paths are
# lower-case with backslashes (see util.key). This is a guess from file types only: it never reads mod pages.
def _under(p: str, prefix: str, *exts: str) -> bool:
    return p.startswith(prefix) and (not exts or p.endswith(exts))


NEEDS_RULES = {
    "RED4ext": lambda p: _under(p, "red4ext\\plugins\\"),
    "Redscript": lambda p: _under(p, "r6\\scripts\\", ".reds"),
    "ArchiveXL": lambda p: _under(p, "archive\\", ".xl"),
    "TweakXL": lambda p: _under(p, "r6\\tweaks\\", ".yaml", ".yml", ".tweak"),
    "Cyber Engine Tweaks": lambda p: _under(p, "bin\\x64\\plugins\\cyber_engine_tweaks\\mods\\"),
    "Input Loader": lambda p: _under(p, "r6\\input\\", ".xml"),
    "Audioware": lambda p: _under(p, "r6\\audioware\\"),
}
PROVIDES_RULES = {
    "RED4ext": lambda p: p == "red4ext\\red4ext.dll",
    "Redscript": lambda p: _under(p, "red4ext\\plugins\\redscript\\") or p == "engine\\tools\\scc.exe",
    "ArchiveXL": lambda p: _under(p, "red4ext\\plugins\\archivexl\\"),
    "TweakXL": lambda p: _under(p, "red4ext\\plugins\\tweakxl\\"),
    "Cyber Engine Tweaks": lambda p: p == "bin\\x64\\plugins\\cyber_engine_tweaks.asi",
    "Input Loader": lambda p: _under(p, "red4ext\\plugins\\input_loader\\") or _under(p, "red4ext\\plugins\\inputloader\\"),
    "Audioware": lambda p: _under(p, "red4ext\\plugins\\audioware\\"),
}


def detect_frameworks(file_keys) -> tuple:
    """(needs, provides): framework names a mod needs and framework names it supplies, from its file paths."""
    keys = list(file_keys)
    provides = sorted(n for n, rule in PROVIDES_RULES.items() if any(rule(k) for k in keys))
    needs = sorted(n for n, rule in NEEDS_RULES.items() if n not in provides and any(rule(k) for k in keys))
    return needs, provides


# ---------------------------------------------------------------- model
@dataclass
class Mod:
    id: str
    name: str
    group: str
    framework: bool
    requires: list
    path: Path
    files: dict = field(default_factory=dict)  # key -> relative path (original case)
    size: int = 0
    needs_fw: list = field(default_factory=list)      # framework names guessed from its files (see detect_frameworks)
    provides_fw: list = field(default_factory=list)   # framework names it supplies

    def src(self, rel: str) -> Path:
        return self.path / rel


class Library:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.mods: dict[str, Mod] = {}

    def scan(self) -> dict:
        mods = {}
        if self.root.exists():
            for d in sorted(self.root.iterdir(), key=lambda p: p.name.lower()):
                if not d.is_dir() or d.name.startswith("__") or d.name.lower() in (".git", ".vs", ".idea"):
                    continue
                mods[d.name] = self._load(d)
        self.mods = mods
        return mods

    def _load(self, d: Path) -> Mod:
        meta = read_json(d / META, {}) or {}
        name = meta.get("name") or clean_name(d.name)
        group = meta.get("group") or guess_group(name)
        framework = bool(meta["framework"]) if "framework" in meta else group == "Framework"
        files, size = {}, 0
        for p in d.rglob("*"):
            if p.is_file() and p.name != META:
                rel = norm_rel(str(p.relative_to(d)))
                files[key(rel)] = rel
                try:
                    size += p.stat().st_size
                except OSError:
                    pass
        needs_fw, provides_fw = detect_frameworks(files)
        return Mod(d.name, name, group, framework, list(meta.get("requires", [])), d, files, size, needs_fw, provides_fw)

    def providers(self) -> dict:
        """framework name -> ids of library mods that supply it."""
        out: dict = {}
        for m in self.mods.values():
            for fw in m.provides_fw:
                out.setdefault(fw, []).append(m.id)
        return out

    def auto_requires(self, m: Mod, providers: dict = None) -> list:
        """What the file guess says `m` needs: [{name, ids}] where ids are library mods that supply it (empty = none in
        the library). Left out when the mod's own `requires` already names a supplier."""
        providers = self.providers() if providers is None else providers
        out = []
        for fw in m.needs_fw:
            ids = [i for i in providers.get(fw, []) if i != m.id]
            if not any(i in m.requires for i in ids):
                out.append({"name": fw, "ids": ids})
        return out

    def get(self, mod_id: str) -> Mod:
        return self.mods[mod_id]

    def find(self, text: str) -> str:
        """Find a mod id by exact id, else unique prefix / substring of id or cleaned name (case-insensitive)."""
        t = text.lower()
        for mid in self.mods:
            if mid.lower() == t:
                return mid
        hits = [m.id for m in self.mods.values() if m.name.lower() == t]
        if len(hits) == 1:
            return hits[0]
        hits = [m.id for m in self.mods.values() if m.id.lower().startswith(t) or m.name.lower().startswith(t)]
        if len(hits) == 1:
            return hits[0]
        hits = [m.id for m in self.mods.values() if t in m.id.lower() or t in m.name.lower()]
        if len(hits) == 1:
            return hits[0]
        raise KeyError(f"{'no mod' if not hits else 'ambiguous'} matching {text!r}" + (f": {hits[:6]}" if hits else ""))

    def write_meta(self, mod_id: str, **fields) -> None:
        p = self.root / mod_id / META
        meta = read_json(p, {}) or {}
        meta.update({k: v for k, v in fields.items() if v is not None})
        write_json(p, meta)

    # ------------------------------------------------------------ importing (never executes anything)
    def import_sources(self, sources, name: str, tmp_root: Path, meta=None) -> tuple[str, list]:
        """Merge one or more folders / archives into a single new library mod called `name`.

        Archives are unpacked with 7-Zip into a fresh empty temp folder; nothing from them is run.
        Returns (mod id, warnings).
        """
        safe = re.sub(r'[<>:"/\\|?*]', "_", name).strip()
        if not safe:
            raise ValueError("mod name is empty")
        dest = self.root / safe
        if dest.exists():
            raise FileExistsError(f"library already has a mod called {safe!r}")
        tmp_root = Path(tmp_root)
        work = tmp_root / ("import-" + uuid.uuid4().hex[:8])
        work.mkdir(parents=True)
        warnings = []
        try:
            for i, src in enumerate(sources):
                src = Path(src)
                part = work / f"part{i}"
                part.mkdir()
                if src.is_dir():
                    shutil.copytree(src, part, dirs_exist_ok=True)
                elif src.suffix.lower() in ARCHIVE_EXT:
                    self._extract(src, part)
                else:
                    raise ValueError(f"not a folder or archive: {src}")
                root, w = normalize_root(part)
                warnings += [f"{src.name}: {x}" for x in w]
                shutil.copytree(root, work / "merged", dirs_exist_ok=True)
            merged = work / "merged"
            if not merged.exists() or not any(merged.rglob("*")):
                raise ValueError("nothing to import (empty after unpacking)")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(merged), str(dest))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if meta:
            write_json(dest / META, meta)
        self.mods[safe] = self._load(dest)
        return safe, warnings

    def import_listed(self, game_like_root: Path, listing: list, name: str, meta=None) -> str:
        """Build a library mod from a list of relative paths taken from a folder laid out like the game."""
        safe = re.sub(r'[<>:"/\\|?*]', "_", name).strip()
        dest = self.root / safe
        if dest.exists():
            raise FileExistsError(f"library already has a mod called {safe!r}")
        import os
        for rel in listing:
            src = Path(game_like_root) / rel
            dst = dest / rel
            if not src.is_file():
                raise FileNotFoundError(src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(src, dst)  # same drive: instant, no extra space; immutable mod files
            except OSError:
                shutil.copy2(src, dst)
        if meta:
            write_json(dest / META, meta)
        self.mods[safe] = self._load(dest)
        return safe

    @staticmethod
    def _extract_zip(archive: Path, out: Path) -> None:
        """Plain .zip files need no extra software. Entries that would land outside `out` are refused (zip-slip)."""
        import zipfile
        out_root = out.resolve()
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                target = (out / info.filename).resolve()
                if target != out_root and out_root not in target.parents:
                    raise RuntimeError(f"unsafe path in {archive.name}: {info.filename!r}")
            zf.extractall(out)

    @staticmethod
    def _extract(archive: Path, out: Path) -> None:
        if archive.suffix.lower() == ".zip":
            try:
                Library._extract_zip(archive, out)
                return
            except RuntimeError:
                raise
            except Exception:       # an unusual zip (e.g. a compression method Python lacks): try 7-Zip below
                shutil.rmtree(out, ignore_errors=True)
                out.mkdir(parents=True, exist_ok=True)
        exe = find_7z()
        if not exe:
            raise RuntimeError(f"{archive.suffix.lower()} archives need 7-Zip. Install it with CyberLoader Setup "
                               "(or unpack the mod yourself and drop the folder instead)")
        r = subprocess.run([exe, "x", "-y", "-aos", f"-o{out}", str(archive)], capture_output=True, text=True,
                           creationflags=CREATE_NO_WINDOW)
        if r.returncode not in (0, 1):  # 1 = warnings only
            raise RuntimeError(f"7-Zip failed on {archive.name}: {r.stdout[-300:]} {r.stderr[-300:]}")


def normalize_root(folder: Path) -> tuple[Path, list]:
    """Descend through wrapper folders until the game-style roots (archive, bin, r6, ...) appear."""
    root = folder
    for _ in range(6):
        names = {c.name.lower() for c in root.iterdir()}
        if names & GAME_ROOTS:
            break
        kids = [c for c in root.iterdir() if c.is_dir()]
        if len(kids) == 1 and not any(c.is_file() for c in root.iterdir()):
            root = kids[0]
        else:
            break
    warnings = []
    for c in root.iterdir():
        if c.name.lower() not in GAME_ROOTS:
            warnings.append(f"'{c.name}' is not a game folder; it will be placed in the game's root")
    return root, warnings
