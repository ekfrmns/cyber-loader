import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def key(rel: str) -> str:
    """Case-insensitive, separator-normalised key for a game-relative path (Windows semantics)."""
    return rel.replace("/", "\\").lower()


def norm_rel(rel: str) -> str:
    return rel.replace("/", "\\").strip("\\")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default


def write_json(path, obj) -> None:
    """Atomic write: temp file in the same folder, then replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=1)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sha256(path, bufsize: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def process_running(image: str) -> bool:
    """True if a process with this image name (e.g. 'Cyberpunk2077.exe') is running. Windows only."""
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=15,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return image.lower() in out.lower()


def pid_alive(pid: int) -> bool:
    if os.name != "nt" or not pid:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], capture_output=True, text=True,
                             creationflags=CREATE_NO_WINDOW, timeout=15).stdout
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return str(int(pid)) in out


def find_7z() -> str | None:
    """7-Zip: the private copy Setup installs next to the app (<root>\\tools\\7z), then PATH, then a normal install."""
    import shutil
    from .config import install_root
    root = install_root()
    for cand in (
        str(root / "tools" / "7z" / "7z.exe") if root else None,
        shutil.which("7z"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ):
        if cand and Path(cand).exists():
            return cand
    return None
