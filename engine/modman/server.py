"""Local HTTP server: serves ui/ and the JSON API described in docs/API.md. Bound to 127.0.0.1 only."""
import json
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .app import ApiError, App
from .util import CREATE_NO_WINDOW, pid_alive, read_json, write_json


def make_handler(app: App, port_box: dict):
    ui = app.cfg.ui

    class Handler(BaseHTTPRequestHandler):
        server_version = "modman/0.1"

        def log_message(self, *a):  # keep the console quiet
            pass

        # -- security: only our own origin may talk to us (stops other web pages driving the API)
        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            return host in (f"127.0.0.1:{port_box['port']}", f"localhost:{port_box['port']}")

        def _origin_ok(self) -> bool:
            o = self.headers.get("Origin")
            return not o or o.lower() in (f"http://127.0.0.1:{port_box['port']}", f"http://localhost:{port_box['port']}")

        def _send(self, code, body, ctype="application/json", extra=None):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _json_body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                raise ApiError(413, "request too large")
            if n and "application/json" not in (self.headers.get("Content-Type") or ""):
                raise ApiError(415, "send JSON")
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def do_PUT(self):
            self._handle("PUT")

        def _upload_file(self):
            """PUT /api/import/file?token=..&path=..  raw bytes, streamed to disk (files can be hundreds of MB)."""
            q = parse_qs(urlparse(self.path).query)
            token, rel = (q.get("token") or [""])[0], (q.get("path") or [""])[0]
            n = int(self.headers.get("Content-Length") or -1)
            if n < 0:
                raise ApiError(411, "Content-Length is required")
            up, dest = app.import_target(token, rel)
            if up["bytes"] + n > app.MAX_UPLOAD_BYTES:
                raise ApiError(413, "import is too large")
            dest.parent.mkdir(parents=True, exist_ok=True)
            left = n
            with open(dest, "wb") as f:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        raise ApiError(400, "upload ended early")
                    f.write(chunk)
                    left -= len(chunk)
            up["bytes"] += n
            up["files"] += 1
            return {"ok": True}

        def _handle(self, method):
            app.last_request = time.time()
            if not self._host_ok() or not self._origin_ok():
                return self._send(403, {"error": "forbidden"})
            path = urlparse(self.path).path
            try:
                if method == "PUT":
                    if path != "/api/import/file":
                        return self._send(405, {"error": "method not allowed"})
                    return self._send(200, self._upload_file())
                if path.startswith("/api/"):
                    out = route(app, method, path, self._json_body() if method == "POST" else {})
                    return self._send(200, out)
                if method != "GET":
                    return self._send(405, {"error": "method not allowed"})
                return self._static(path)
            except ApiError as e:
                self._send(e.code, {"error": e.message})
            except (KeyError, ValueError) as e:
                self._send(400, {"error": str(e).strip("'\"")})
            except Exception as e:  # never crash the server
                self._send(500, {"error": f"internal error: {e}"})

        def _static(self, path):
            rel = unquote(path).lstrip("/") or "index.html"
            p = (ui / rel).resolve()
            try:
                p.relative_to(ui.resolve())
            except ValueError:
                return self._send(403, {"error": "forbidden"})
            if not p.is_file():
                return self._send(404, {"error": "not found"})
            ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            if p.suffix in (".js", ".mjs"):
                ctype = "text/javascript"
            self._send(200, p.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))

    return Handler


def route(app: App, method: str, path: str, body: dict):
    P = path
    if method == "GET":
        if P == "/api/state":
            return app.state_view()
        if P == "/api/progress":
            return dict(app.job)
        if P == "/api/settings":
            return app.cfg.settings()
        if P == "/api/trash":
            return app.list_trash()
        if P == "/api/snapshots":
            return app.list_snapshots()
        if P.startswith("/api/snapshots/"):
            return app.get_snapshot(P[len("/api/snapshots/"):])
        raise ApiError(404, "unknown endpoint")
    if P == "/api/toggle":
        return app.toggle(str(body["id"]), bool(body["enabled"]))
    if P == "/api/profile/select":
        return app.select_profile(str(body["name"]))
    if P == "/api/profile/save":
        app.save_profile(str(body["name"]))
        return {"ok": True}
    if P == "/api/profile/new":
        app.new_profile(str(body["name"]), body.get("from"))
        return {"ok": True}
    if P == "/api/profile/rename":
        return app.rename_profile(str(body["name"]), str(body["to"]))
    if P == "/api/profile/delete":
        app.delete_profile(str(body["name"]))
        return {"ok": True}
    if P == "/api/preview":
        return app.preview()
    if P == "/api/apply":
        app.start_apply()
        return {"ok": True}
    if P == "/api/import":
        return app.import_path(str(body["path"]))
    if P == "/api/import/begin":
        return app.import_begin(str(body.get("name", "")), str(body.get("kind", "")))
    if P == "/api/import/finish":
        return app.import_finish(str(body.get("token", "")))
    if P == "/api/discard":
        return app.discard()
    if P == "/api/mod/delete":
        return app.delete_mod(str(body["id"]))
    if P == "/api/mod/group":
        return app.set_group(str(body["id"]), str(body.get("group", "")))
    if P == "/api/mod/requires":
        return app.set_requires(str(body["id"]), body.get("requires"))
    if P == "/api/snapshots/save":
        return app.save_snapshot(str(body.get("name") or ""))
    if P == "/api/snapshots/restore":
        return app.restore_snapshot(str(body["id"]))
    if P == "/api/snapshots/pin":
        return app.pin_snapshot(str(body["id"]), bool(body.get("pinned", True)), body.get("name"))
    if P == "/api/trash/restore":
        return app.restore_trash(str(body["id"]))
    if P == "/api/trash/empty":
        return app.empty_trash(str(body["id"]) if body.get("id") else None)
    if P == "/api/settings":
        return app.cfg.update_settings(body.get("theme"), body.get("accent"))
    raise ApiError(404, "unknown endpoint")


def find_edge() -> str | None:
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", shutil.which("msedge")):
        if c and Path(c).exists():
            return c
    return None


def _open_window(url: str) -> None:
    edge = find_edge()
    if edge:
        subprocess.Popen([edge, f"--app={url}", "--window-size=1100,740"], creationflags=CREATE_NO_WINDOW)
    else:
        import webbrowser
        webbrowser.open(url)


def _answers(port: int) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/settings", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def _busy(port: int) -> bool:
    """True if the running instance is in the middle of an apply (never replace it then)."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/progress", timeout=2) as r:
            return json.loads(r.read()).get("state") == "running"
    except (OSError, ValueError):
        return True  # cannot tell: be safe and keep it


def serve(app: App, port: int = 0, open_window: bool = True, idle_exit: int = 0,
          host_managed: bool = False, parent_pid: int = 0):
    """Run the app. One instance only: a second launch just opens a window on the running one.
    With idle_exit > 0 the server quits that many seconds after the last request (i.e. after the window is closed).
    host_managed: CyberLoader.exe owns the window and the single-instance rule; the server just serves on the given
    port and quits when the host process (parent_pid) is gone."""
    info = app.cfg.state_dir / "server.json"
    prev = None if host_managed else read_json(info)
    if prev and pid_alive(prev.get("pid", 0)) and _answers(prev.get("port", 0)):
        if prev.get("version") == __version__ or _busy(prev["port"]):
            print(f"Already running on port {prev['port']}")
            if open_window:
                _open_window(f"http://127.0.0.1:{prev['port']}/")
            return
        # an older version is still running (e.g. right after an upgrade) and idle: replace it
        print(f"Replacing running version {prev.get('version', 'unknown')} with {__version__}")
        subprocess.run(["taskkill", "/PID", str(int(prev["pid"])), "/F"], capture_output=True, creationflags=CREATE_NO_WINDOW)
        time.sleep(1)
    box = {"port": 0}
    httpd = ThreadingHTTPServer(("127.0.0.1", port), None)
    box["port"] = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler(app, box)
    url = f"http://127.0.0.1:{box['port']}/"
    if not host_managed:
        write_json(info, {"pid": os.getpid(), "port": box["port"], "version": __version__})
    app.last_request = time.time()
    print(f"Cyberpunk Mod Manager {__version__} running at {url}  (Ctrl+C to stop)", flush=True)

    def watch_parent():
        while True:
            time.sleep(3)
            if not pid_alive(parent_pid):
                httpd.shutdown()
                return

    if host_managed and parent_pid:
        threading.Thread(target=watch_parent, daemon=True).start()

    def watch():
        while True:
            time.sleep(5)
            idle = time.time() - app.last_request
            if idle > idle_exit and app.job.get("state") != "running":
                httpd.shutdown()
                return

    if idle_exit > 0:
        threading.Thread(target=watch, daemon=True).start()
    if open_window:
        _open_window(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        cur = None if host_managed else read_json(info)
        if cur and cur.get("pid") == os.getpid():
            try:
                info.unlink()
            except OSError:
                pass
