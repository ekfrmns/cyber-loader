import argparse
import re
import sys
import time
from pathlib import Path

from .app import ApiError, App
from .config import Config
from .deploy import preflight
from .library import META
from .util import write_json


def cmd_status(app: App, a):
    s = app.state_view()
    pf = preflight(app.cfg)
    print(f"game: {app.cfg.game}  running={pf['game_running']}  vortex running={pf['vortex_running']}")
    print(f"library: {app.cfg.library}  ({len(app.library.mods)} mods)")
    print(f"selected profile: {s['profile']}   deployed files: {s['deployedCount']}   pending: {s['pendingCount']}")
    print("profiles: " + ", ".join(f"{n} ({len(app.profiles.load(n))})" for n in s["profiles"]))


def cmd_mods(app: App, a):
    on = set(app.working)
    for m in app.library.mods.values():
        if a.enabled and m.id not in on:
            continue
        print(f"{'[x]' if m.id in on else '[ ]'} {m.group:<10} {len(m.files):>5} files  {m.name}")


def cmd_plan(app: App, a):
    if a.profile:
        app.select_profile(a.profile)
    p = app.plan()
    print(f"profile {app.current!r}: {p.summary()}")
    for label, items in (("BLOCKED", [(b['rel'], b['reason']) for b in p.blocked]),
                         ("LEFT IN PLACE", [(b['rel'], b['reason']) for b in p.left])):
        for rel, why in items[:15]:
            print(f"  {label}: {rel}  ({why})")
        if len(items) > 15:
            print(f"  ... and {len(items) - 15} more {label}")
    for c in p.conflicts[:10]:
        print(f"  conflict: {c['path']}  winner={c['winner']}  losers={c['losers']}")
    if a.verbose:
        for e in p.adds[:50]:
            print(f"  + {e.rel}  ({e.mod})")
        for k, r in p.removes[:50]:
            print(f"  - {r['rel']}  ({r['mod']})")
    return p


def cmd_apply(app: App, a):
    p = cmd_plan(app, a)
    pf = preflight(app.cfg)
    if pf["game_running"]:
        sys.exit("The game is running. Close it first.")
    if pf["vortex_running"]:
        print("warning: Vortex is running; close it so it cannot touch the game folder.")
    if p.blocked:
        sys.exit("Blocked files present; nothing changed.")
    if not a.yes:
        print("Dry run only. Add --yes to apply.")
        return
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    logf = open(app.cfg.logs_dir / f"apply-{stamp}.log", "w", encoding="utf-8")
    res = app.apply_blocking(progress=lambda pct, t: print(f"\r{pct:3d}% {t[:60]:<60}", end="", flush=True),
                             log=lambda m: logf.write(m + "\n"))
    logf.close()
    print(f"\nDone. errors={len(res['errors'])}  log: logs\\apply-{stamp}.log")
    for e in res["errors"][:10]:
        print("  ", e)


def cmd_adopt(app: App, a):
    r = app.adopt_vortex(Path(a.manifest), Path(a.staging) if a.staging else None)
    print(f"adopted {r['files']} deployed files from {r['mods']} mods ({r['missing']} listed but missing on disk)")
    print("created profile 'Vortex import' and selected it")


def cmd_import(app: App, a):
    mid, warns = app.library.import_sources([Path(s) for s in a.sources], a.name, app.cfg.tmp_dir)
    meta = {k: v for k, v in (("group", a.group), ("requires", a.requires or None)) if v}
    if meta:
        app.library.write_meta(mid, **meta)
    print(f"imported {mid!r} ({len(app.library.mods[mid].files)} files)")
    for w in warns:
        print("  warning:", w)


def cmd_cleanup_vortex(app: App, a):
    """Move Vortex's leftover marker/backup files out of the game folder (moved, never deleted)."""
    import shutil
    game = app.cfg.game
    dest = app.cfg.state_dir / "vortex-leftovers"
    found = [p for p in game.rglob("*") if p.is_file() and (p.name == "__folder_managed_by_vortex" or p.name.endswith(".vortex_backup"))]
    marker_dirs = set()
    for p in found:
        if not a.quiet:
            print(("moving " if a.yes else "would move ") + str(p.relative_to(game)))
        if a.yes:
            t = dest / p.relative_to(game)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(t))
            if p.name == "__folder_managed_by_vortex":
                marker_dirs.add(p.parent)
    removed = 0
    if a.yes:  # folders Vortex created and marked, now empty, go too (deepest first; never the game root)
        for d in sorted(marker_dirs, key=lambda x: len(x.parts), reverse=True):
            try:
                if d != game and d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
                    removed += 1
            except OSError:
                pass
    print(f"{len(found)} file(s)" + (f" moved to {dest}; {removed} empty folder(s) removed" if a.yes else ". Add --yes to move them."))


def cmd_serve(app: App, a):
    from .server import serve
    serve(app, a.port, not a.no_open, a.idle_exit, a.host_managed, a.parent_pid)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="modman", description="Cyberpunk Mod Manager engine")
    ap.add_argument("--game")
    ap.add_argument("--data")
    ap.add_argument("--library")
    ap.add_argument("--ui", help="folder to serve the UI from (default: the ui folder next to engine)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("mods"); s.add_argument("--enabled", action="store_true"); s.set_defaults(fn=cmd_mods)
    s = sub.add_parser("plan"); s.add_argument("profile", nargs="?"); s.add_argument("-v", "--verbose", action="store_true"); s.set_defaults(fn=cmd_plan)
    s = sub.add_parser("apply"); s.add_argument("profile", nargs="?"); s.add_argument("--yes", action="store_true")
    s.add_argument("-v", "--verbose", action="store_true"); s.set_defaults(fn=cmd_apply)
    s = sub.add_parser("adopt-vortex"); s.add_argument("--manifest", required=True, help="path of Vortex's vortex.deployment.msgpack"); s.add_argument("--staging"); s.set_defaults(fn=cmd_adopt)
    s = sub.add_parser("import"); s.add_argument("--name", required=True); s.add_argument("--group"); s.add_argument("--requires", nargs="*")
    s.add_argument("sources", nargs="+"); s.set_defaults(fn=cmd_import)
    s = sub.add_parser("cleanup-vortex"); s.add_argument("--yes", action="store_true"); s.add_argument("--quiet", action="store_true"); s.set_defaults(fn=cmd_cleanup_vortex)
    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=0); s.add_argument("--no-open", action="store_true")
    s.add_argument("--idle-exit", type=int, default=0, help="quit this many seconds after the last request (0 = never)")
    s.add_argument("--host-managed", action="store_true", help="CyberLoader.exe owns the window; no single-instance file, no window")
    s.add_argument("--parent-pid", type=int, default=0, help="with --host-managed: quit when this process is gone")
    s.set_defaults(fn=cmd_serve)
    a = ap.parse_args(argv)
    app = App(Config(game=a.game, data=a.data, library=a.library, ui=a.ui))
    try:
        a.fn(app, a)
    except (ApiError, KeyError, ValueError, FileExistsError, RuntimeError) as ex:
        sys.exit(f"error: {getattr(ex, 'message', ex)}")
