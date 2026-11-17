import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modman.app import App, order_for_owners
from modman.config import Config
from modman.server import make_handler


def write(p: Path, text="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modman-api-"))
        game, data, ui = self.tmp / "game", self.tmp / "data", self.tmp / "ui"
        write(game / "bin" / "x64" / "Cyberpunk2077.exe")
        write(ui / "index.html", "<html>ok</html>")
        cfg = Config(game=game, data=data, ui=ui)
        cfg.ensure()
        write(cfg.library / "Core" / "red4ext" / "core.dll", "core")
        write(cfg.library / "Fancy" / "archive" / "pc" / "mod" / "fancy.archive", "fancy")
        write(cfg.library / "Fancy" / ".mod.json", json.dumps({"requires": ["Core"], "group": "Content"}))
        self.app = App(cfg)
        self.app.profiles.save("Empty", [])
        self.app.profiles.save("Both", ["Core", "Fancy"])
        self.app.select_profile("Empty")
        box = {"port": 0}
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        box["port"] = self.httpd.server_address[1]
        self.httpd.RequestHandlerClass = make_handler(self.app, box)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{box['port']}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"null") if r.headers["Content-Type"].startswith("application/json") else r.read()
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_state_shape(self):
        code, s = self.call("GET", "/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(s["profile"], "Empty")
        self.assertRegex(s["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(set(s["profiles"]), {"Empty", "Both"})
        m = {x["id"]: x for x in s["mods"]}
        self.assertEqual(m["Fancy"]["requires"], ["Core"])
        self.assertEqual(m["Fancy"]["group"], "Content")
        self.assertEqual(set(m["Core"]), {"id", "name", "group", "files", "enabled", "pending", "framework",
                                          "requires", "conflicts"})

    def test_toggle_preview_apply_cycle(self):
        code, r = self.call("POST", "/api/toggle", {"id": "Fancy", "enabled": True})
        self.assertEqual(code, 200)
        self.assertTrue(any("needs Core" in w for w in r["warnings"]))
        self.assertEqual(r["mod"]["pending"], "on")
        self.call("POST", "/api/toggle", {"id": "Core", "enabled": True})
        code, p = self.call("POST", "/api/preview")
        self.assertEqual((p["add"], p["remove"]), (2, 0))
        self.assertEqual(self.call("POST", "/api/apply")[0], 200)
        for _ in range(100):
            _, pr = self.call("GET", "/api/progress")
            if pr["state"] in ("done", "error"):
                break
            time.sleep(0.05)
        self.assertEqual(pr["state"], "done", pr)
        self.assertTrue((self.app.cfg.game / "archive" / "pc" / "mod" / "fancy.archive").exists())
        _, s = self.call("GET", "/api/state")
        self.assertEqual(s["deployedCount"], 2)
        self.assertEqual(s["pendingCount"], {"on": 0, "off": 0})
        self.call("POST", "/api/profile/select", {"name": "Empty"})
        _, p = self.call("POST", "/api/preview")
        self.assertEqual((p["add"], p["remove"]), (0, 2))

    def test_profiles_crud(self):
        self.call("POST", "/api/toggle", {"id": "Core", "enabled": True})
        self.assertEqual(self.call("POST", "/api/profile/save", {"name": "Mine"})[0], 200)
        self.assertEqual(self.call("POST", "/api/profile/new", {"name": "Copy", "from": "Mine"})[0], 200)
        self.assertEqual(self.call("POST", "/api/profile/new", {"name": "Copy"})[0], 409)
        self.assertEqual(self.call("POST", "/api/profile/delete", {"name": "Copy"})[0], 200)
        self.assertEqual(self.call("POST", "/api/profile/select", {"name": "nope"})[0], 404)

    def test_profile_rename(self):
        self.call("POST", "/api/profile/select", {"name": "Both"})
        code, r = self.call("POST", "/api/profile/rename", {"name": "Both", "to": "  My favourites "})
        self.assertEqual(code, 200, r)
        self.assertEqual(r["profile"], "My favourites")
        self.assertEqual(r["profiles"], ["Empty", "My favourites"])   # order kept
        _, s = self.call("GET", "/api/state")
        self.assertEqual((s["profile"], s["profiles"]), ("My favourites", ["Empty", "My favourites"]))
        self.assertEqual({m["id"] for m in s["mods"] if m["enabled"]}, {"Core", "Fancy"})
        self.assertFalse(s["profileDirty"])
        self.assertEqual(self.call("POST", "/api/profile/rename", {"name": "Both", "to": "x"})[0], 404)
        self.assertEqual(self.call("POST", "/api/profile/rename", {"name": "My favourites", "to": "empty"})[0], 409)
        self.assertEqual(self.call("POST", "/api/profile/rename", {"name": "My favourites", "to": "   "})[0], 400)
        code, r = self.call("POST", "/api/profile/rename", {"name": "My favourites", "to": "my FAVOURITES"})   # case-only change
        self.assertEqual((code, r["profile"]), (200, "my FAVOURITES"))

    def test_trash_delete_restore_empty(self):
        lib = self.app.cfg.library
        code, r = self.call("POST", "/api/mod/delete", {"id": "Fancy"})
        self.assertEqual(code, 200, r)
        self.assertFalse((lib / "Fancy").exists())
        _, s = self.call("GET", "/api/state")
        self.assertEqual([m["id"] for m in s["mods"]], ["Core"])
        _, t = self.call("GET", "/api/trash")
        self.assertEqual([(i["name"], i["files"]) for i in t["items"]], [("Fancy", 1)])
        self.assertGreater(t["totalSize"], 0)
        # the profile keeps its entry, so restoring brings the mod back into it
        self.call("POST", "/api/profile/select", {"name": "Both"})
        self.assertEqual(self.call("POST", "/api/mod/delete", {"id": "Fancy"})[0], 404)
        code, r = self.call("POST", "/api/trash/restore", {"id": t["items"][0]["id"]})
        self.assertEqual((code, r["id"]), (200, "Fancy"))
        self.assertTrue((lib / "Fancy" / "archive" / "pc" / "mod" / "fancy.archive").exists())
        self.assertTrue((lib / "Fancy" / ".mod.json").exists())          # its settings travelled with it
        self.assertEqual(self.call("GET", "/api/trash")[1]["items"], [])
        self.call("POST", "/api/profile/select", {"name": "Both"})
        _, s = self.call("GET", "/api/state")
        self.assertEqual({m["id"] for m in s["mods"] if m["enabled"]}, {"Core", "Fancy"})
        # delete again, then empty the trash for good
        self.call("POST", "/api/profile/select", {"name": "Empty"})
        self.call("POST", "/api/mod/delete", {"id": "Fancy"})
        _, t = self.call("GET", "/api/trash")
        code, r = self.call("POST", "/api/trash/empty", {})
        self.assertEqual((code, r["removed"]), (200, 1))
        self.assertEqual(self.call("GET", "/api/trash")[1]["items"], [])
        self.assertFalse((self.app.trash_root / t["items"][0]["id"]).exists())

    def test_trash_refuses_deployed_mods_and_bad_ids(self):
        self.call("POST", "/api/toggle", {"id": "Core", "enabled": True})
        self.call("POST", "/api/apply")
        for _ in range(100):
            if self.call("GET", "/api/progress")[1]["state"] in ("done", "error"):
                break
            time.sleep(0.05)
        code, r = self.call("POST", "/api/mod/delete", {"id": "Core"})
        self.assertEqual(code, 409)
        self.assertIn("Turn it off", r["error"])
        self.assertTrue((self.app.cfg.library / "Core").exists())
        for bad in ("../x", "..\\x", "20250101-000000-zzzz", ""):
            self.assertIn(self.call("POST", "/api/trash/restore", {"id": bad})[0], (400, 404))
        self.assertEqual(self.call("POST", "/api/trash/empty", {"id": "../../data"})[0], 400)

    def test_trash_restore_never_overwrites(self):
        self.call("POST", "/api/mod/delete", {"id": "Fancy"})
        write(self.app.cfg.library / "Fancy" / "archive" / "pc" / "mod" / "other.archive", "new mod with the same name")
        self.app.library.scan()
        tid = self.call("GET", "/api/trash")[1]["items"][0]["id"]
        code, r = self.call("POST", "/api/trash/restore", {"id": tid})
        self.assertEqual((code, r["id"]), (200, "Fancy (restored)"))
        self.assertTrue((self.app.cfg.library / "Fancy" / "archive" / "pc" / "mod" / "other.archive").exists())

    def test_settings_validation(self):
        code, s = self.call("POST", "/api/settings", {"theme": "dark", "accent": "#ff00aa"})
        self.assertEqual((code, s["theme"], s["accent"]), (200, "dark", "#ff00aa"))
        self.assertEqual(self.call("POST", "/api/settings", {"theme": "neon"})[0], 400)
        self.assertEqual(self.call("POST", "/api/settings", {"accent": "red"})[0], 400)

    def test_security_and_static(self):
        code, body = self.call("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn(b"ok", body)
        self.assertEqual(self.call("GET", "/../../etc/passwd")[0] in (403, 404), True)
        self.assertEqual(self.call("GET", "/api/state", headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.call("GET", "/api/state", headers={"Host": "evil.example"})[0], 403)

    def put(self, path, data):
        req = urllib.request.Request(self.base + path, method="PUT", data=data,
                                     headers={"Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_profile_dirty_and_discard(self):
        _, s = self.call("GET", "/api/state")
        self.assertFalse(s["profileDirty"])
        self.call("POST", "/api/toggle", {"id": "Core", "enabled": True})
        _, s = self.call("GET", "/api/state")
        self.assertTrue(s["profileDirty"])
        code, s = self.call("POST", "/api/discard")
        self.assertEqual(code, 200)
        self.assertEqual(s["pendingCount"], {"on": 0, "off": 0})
        self.assertFalse([m for m in s["mods"] if m["enabled"]])

    def test_preview_lists_files(self):
        self.call("POST", "/api/toggle", {"id": "Fancy", "enabled": True})
        _, p = self.call("POST", "/api/preview")
        self.assertEqual(p["files"]["add"], [{"id": "Fancy", "path": r"archive\pc\mod\fancy.archive"}])
        self.assertEqual(p["files"]["remove"], [])
        self.assertFalse(p["filesTruncated"])

    def test_folder_upload_import(self):
        code, r = self.call("POST", "/api/import/begin", {"name": "My Mod", "kind": "folder"})
        self.assertEqual(code, 200)
        t = r["token"]
        self.assertEqual(self.put(f"/api/import/file?token={t}&path=archive/pc/mod/x.archive", b"data")[0], 200)
        self.assertEqual(self.put(f"/api/import/file?token={t}&path=r6/scripts/X/x.reds", b"reds")[0], 200)
        code, r = self.call("POST", "/api/import/finish", {"token": t})
        self.assertEqual(code, 200, r)
        self.assertEqual(r["id"], "My Mod")
        lib = self.app.cfg.library / "My Mod"
        self.assertEqual((lib / "archive" / "pc" / "mod" / "x.archive").read_bytes(), b"data")
        self.assertEqual(self.call("POST", "/api/import/finish", {"token": t})[0], 404)  # token is single-use
        _, s = self.call("GET", "/api/state")
        self.assertIn("My Mod", [m["id"] for m in s["mods"]])

    def test_upload_rejects_unsafe_paths(self):
        _, r = self.call("POST", "/api/import/begin", {"name": "Evil", "kind": "folder"})
        t = r["token"]
        for bad in ("../escape.txt", "..%5C..%5Cescape.txt", "/abs.txt", "C:/abs.txt", "a/../../b.txt", "a%3Ab.txt"):
            code, body = self.put(f"/api/import/file?token={t}&path={bad}", b"x")
            self.assertEqual(code, 400, (bad, body))
        self.assertFalse((self.app.cfg.tmp_dir / "escape.txt").exists())
        self.assertEqual(self.put("/api/import/file?token=nope&path=a.txt", b"x")[0], 404)
        self.assertEqual(self.put("/api/other", b"x")[0], 405)
        self.assertEqual(self.call("POST", "/api/import/begin", {"name": "x", "kind": "weird"})[0], 400)

    @unittest.skipUnless(__import__("modman.util", fromlist=["find_7z"]).find_7z(), "7-Zip not installed")
    def test_archive_upload_import(self):
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("Wrapper/archive/pc/mod/y.archive", "yy")
        _, r = self.call("POST", "/api/import/begin", {"name": "Foo-1234-1-0-1700000000.zip", "kind": "archive"})
        t = r["token"]
        self.assertEqual(self.put(f"/api/import/file?token={t}&path=Foo-1234-1-0-1700000000.zip", buf.getvalue())[0], 200)
        self.assertEqual(self.put(f"/api/import/file?token={t}&path=Second.zip", buf.getvalue())[0], 400)
        code, r = self.call("POST", "/api/import/finish", {"token": t})
        self.assertEqual(code, 200, r)
        self.assertEqual(r["id"], "Foo")
        self.assertTrue((self.app.cfg.library / "Foo" / "archive" / "pc" / "mod" / "y.archive").exists())

    def test_conflict_ordering_helper(self):
        L = self.app.library
        write(L.root / "X" / "r6" / "s.reds", "x")
        write(L.root / "Y" / "r6" / "s.reds", "y")
        L.scan()
        order = order_for_owners(L, ["X", "Y"], {r"r6\s.reds": "X"})
        self.assertEqual(order, ["Y", "X"])  # the owner (X) must come last so it wins


if __name__ == "__main__":
    unittest.main()
