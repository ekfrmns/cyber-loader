import os
import time
from pathlib import Path

from .util import read_json, write_json

GAME_EXE = "Cyberpunk2077.exe"
GAME_EXE_REL = Path("bin") / "x64" / GAME_EXE
CONFIG_NAME = "cyberloader.json"
NOT_SET = Path("(Cyberpunk 2077 folder not set)")


def find_install_config():
    """The install's config file, written by Setup: {"game": "<Cyberpunk 2077 folder>", "data": "<data folder>"}.
    It sits in the install root, a few folders above this file (<root>\\versions\\<ver>\\engine\\modman\\config.py).
    CYBERLOADER_CONFIG overrides the search (development, tests)."""
    env = os.environ.get("CYBERLOADER_CONFIG")
    if env:
        return Path(env) if Path(env).is_file() else None
    for p in Path(__file__).resolve().parents[:6]:
        c = p / CONFIG_NAME
        if c.is_file():
            return c
    return None


def install_root():
    c = find_install_config()
    return c.parent if c else None


def _find_ui() -> Path:
    here = Path(__file__).resolve().parents[2]  # repo root, or <root>\versions\<ver> when installed
    return here / "ui"


def _exe_product_version(path: Path):
    """The ProductVersion text of a Windows exe (Cyberpunk's is the game version, like "2.5"), or None."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.WinDLL("version", use_last_error=True)
        size = ver.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(str(path), 0, size, buf):
            return None
        p, n = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(p), ctypes.byref(n)) or n.value < 4:
            return None
        lang, cp = ctypes.cast(p, ctypes.POINTER(ctypes.c_ushort * 2)).contents
        if not ver.VerQueryValueW(buf, f"\\StringFileInfo\\{lang:04x}{cp:04x}\\ProductVersion", ctypes.byref(p), ctypes.byref(n)) or not n.value:
            return None
        return ctypes.wstring_at(p.value, n.value - 1).strip() or None
    except Exception:
        return None


def game_info_for(game: Path) -> dict:
    """{version, updated} of the game installed in `game`, read from its exe (best effort; {} if it cannot be read)."""
    exe = Path(game) / GAME_EXE_REL
    out = {}
    try:
        out["updated"] = time.strftime("%Y-%m-%d", time.localtime(exe.stat().st_mtime))
    except OSError:
        return {}
    v = _exe_product_version(exe)
    if v:
        out["version"] = v
    return out


def check_game_folder(raw) -> dict:
    """Look at a path someone typed or picked. Never changes anything. Returns
    {path, isFolder, found, message, version?, updated?}; `path` is the cleaned-up folder (quotes removed; if they gave the
    exe, or its bin or bin/x64 folder, the main game folder above it). `found` = it holds bin/x64/Cyberpunk2077.exe."""
    text = str(raw or "").strip().strip('"').strip()
    out = {"path": text, "isFolder": False, "found": False}
    if not text:
        out["message"] = "Paste the full path of your Cyberpunk 2077 folder."
        return out
    p = Path(text)
    if not p.is_absolute():
        out["message"] = "Use the full path, starting with the drive letter, like C:\\Games\\Cyberpunk 2077."
        return out
    if p.is_file() and p.name.lower() == GAME_EXE.lower() and len(p.parents) >= 3:
        p = p.parents[2]                                                  # .../bin/x64/Cyberpunk2077.exe -> the game folder
    elif p.is_dir() and not (p / GAME_EXE_REL).is_file():
        for up in (p.parent.parent if p.name.lower() == "x64" else None, p.parent if p.name.lower() == "bin" else None):
            if up and (up / GAME_EXE_REL).is_file():
                p = up
                break
    out["path"] = str(p)
    if not p.exists():
        out["message"] = "That folder doesn’t exist."
        return out
    if not p.is_dir():
        out["message"] = "That is a file, not a folder."
        return out
    out["isFolder"] = True
    if not (p / GAME_EXE_REL).is_file():
        out["message"] = ("This doesn’t look like Cyberpunk 2077: bin\\x64\\Cyberpunk2077.exe isn’t in it. "
                          "Choose the main game folder, the one that contains the bin folder.")
        return out
    out["found"] = True
    out["message"] = "Cyberpunk 2077 found."
    out.update(game_info_for(p))
    return out


class Config:
    """Paths and settings. `data` holds library/, profiles/, state/, logs/ and settings.json.
    Where things come from, first match wins: constructor arguments, MODMAN_GAME / MODMAN_DATA, the install's
    cyberloader.json, then (data only) a folder under the user's local app data."""

    def __init__(self, game=None, data=None, ui=None, library=None, link_min_bytes=1 << 20):
        cfg_file = find_install_config()
        inst = (read_json(cfg_file, {}) or {}) if cfg_file else {}
        game_v = game or os.environ.get("MODMAN_GAME") or inst.get("game")
        # Where the game folder came from: only "config" can be changed from the app (it is saved back into that file)
        self.game_source = "arg" if game else "env" if os.environ.get("MODMAN_GAME") else "config" if inst.get("game") else "none"
        self.config_file = cfg_file
        self.game = Path(game_v) if game_v else NOT_SET
        self.data_source = "arg" if data else "env" if os.environ.get("MODMAN_DATA") else "config"
        data_v = data or os.environ.get("MODMAN_DATA") or inst.get("data") or (str(cfg_file.parent / "data") if cfg_file else None)
        self.data = Path(data_v) if data_v else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CyberLoader" / "data"
        self.settings_file = self.data / "settings.json"
        s = read_json(self.settings_file, {}) or {}
        self.library = Path(library or s.get("library") or self.data / "library")
        self.profiles_dir = self.data / "profiles"
        self.state_dir = self.data / "state"
        self.logs_dir = self.data / "logs"
        self.snapshots_dir = self.data / "snapshots"
        self.tmp_dir = self.data / "tmp"
        self.ui = Path(ui) if ui else _find_ui()
        # Files at least this big are hardlinked; smaller ones are copied so a mod that rewrites its own
        # config in place can never alter the library copy.
        self.link_min_bytes = link_min_bytes

    @property
    def game_found(self) -> bool:
        """True if the configured folder really is a Cyberpunk 2077 install."""
        return (self.game / GAME_EXE_REL).is_file()

    def game_info(self) -> dict:
        """{version, updated} of the installed game, read from its exe (best effort; {} if it cannot be read)."""
        return game_info_for(self.game)

    def game_locked_reason(self):
        """None if the game folder can be changed from the app, else why not (plain words)."""
        if self.game_source in ("arg", "env"):
            return "The game folder was given when this copy was started, so it can’t be changed here."
        if not self.config_file:
            return "This copy has no settings file (it was not installed with Setup), so there is nowhere to save the folder."
        if self.data_source in ("arg", "env"):    # a test or sandbox run: never rewrite the real install's settings file
            return "This copy was started with its own data folder, so the game folder can’t be changed here."
        return None

    def save_game(self, path: Path) -> None:
        """Remember a new game folder: rewrite the install's cyberloader.json atomically, keeping every other key, then use it.
        Raises ValueError/OSError and leaves everything as it was if the file cannot be read or written."""
        why = self.game_locked_reason()
        if why:
            raise ValueError(why)
        try:
            raw = read_json(self.config_file, {})
        except ValueError as ex:
            raise ValueError(f"The settings file is damaged ({ex}); not touching it.")
        if not isinstance(raw, dict):
            raise ValueError("The settings file is not what was expected; not touching it.")
        raw["game"] = str(path)
        write_json(self.config_file, raw, ensure_ascii=False)   # Setup's own reader does not understand \uXXXX escapes
        self.game = Path(path)
        self.game_source = "config"

    def ensure(self) -> None:
        for d in (self.library, self.profiles_dir, self.state_dir, self.logs_dir, self.snapshots_dir, self.tmp_dir):
            d.mkdir(parents=True, exist_ok=True)

    # user-facing settings (theme/accent) live next to engine settings in settings.json
    def settings(self) -> dict:
        s = read_json(self.settings_file, {}) or {}
        return {"theme": s.get("theme", "system"), "accent": s.get("accent", "#0a84ff")}

    def update_settings(self, theme=None, accent=None) -> dict:
        s = read_json(self.settings_file, {}) or {}
        if theme is not None:
            if theme not in ("system", "light", "dark"):
                raise ValueError("theme must be system, light or dark")
            s["theme"] = theme
        if accent is not None:
            import re
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
                raise ValueError("accent must look like #rrggbb")
            s["accent"] = accent
        write_json(self.settings_file, s)
        return self.settings()
