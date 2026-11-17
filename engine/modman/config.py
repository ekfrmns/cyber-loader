import os
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


class Config:
    """Paths and settings. `data` holds library/, profiles/, state/, logs/ and settings.json.
    Where things come from, first match wins: constructor arguments, MODMAN_GAME / MODMAN_DATA, the install's
    cyberloader.json, then (data only) a folder under the user's local app data."""

    def __init__(self, game=None, data=None, ui=None, library=None, link_min_bytes=1 << 20):
        cfg_file = find_install_config()
        inst = (read_json(cfg_file, {}) or {}) if cfg_file else {}
        game_v = game or os.environ.get("MODMAN_GAME") or inst.get("game")
        self.game = Path(game_v) if game_v else NOT_SET
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
